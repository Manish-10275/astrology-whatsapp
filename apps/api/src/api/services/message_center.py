"""Service for Message Center: direct outbound messaging, 24h Meta window checks, and delivery tracking."""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.user import User, UserStatus
from api.db.models.consent import ConsentRecord
from api.db.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    ConversationState,
    MessageDirection,
    MessageSender,
)
from api.db.models.admin import AdminUser
from api.db.models.audit import AuditEvent
from api.services.whatsapp import send_whatsapp_text
from api.services.whatsapp_templates import (
    send_whatsapp_template,
    validate_template_name,
    WhatsAppTemplateError,
)

logger = logging.getLogger("api.services.message_center")

META_WINDOW_HOURS = 24


def mask_phone_number(phone: str) -> str:
    """Masks phone number to protect PII while allowing recognition."""
    clean = phone.strip()
    if len(clean) >= 7:
        prefix = clean[:3]
        suffix = clean[-4:]
        return f"{prefix} •••• ••{suffix}"
    return "••••"


async def get_recipient_window_status(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Calculates whether the recipient is within the 24-hour Meta Customer Service Window."""
    stmt = (
        select(ConversationMessage.created_at)
        .where(
            ConversationMessage.user_id == user_id,
            ConversationMessage.direction == MessageDirection.INBOUND,
        )
        .order_by(desc(ConversationMessage.created_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    last_inbound_at = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not last_inbound_at:
        return {
            "window_active": False,
            "last_inbound_at": None,
            "window_expires_at": None,
            "hours_remaining": 0.0,
        }

    # Ensure last_inbound_at has timezone
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)

    expires_at = last_inbound_at + timedelta(hours=META_WINDOW_HOURS)
    is_active = now < expires_at
    remaining = max(0.0, (expires_at - now).total_seconds() / 3600.0) if is_active else 0.0

    return {
        "window_active": is_active,
        "last_inbound_at": last_inbound_at.isoformat(),
        "window_expires_at": expires_at.isoformat(),
        "hours_remaining": round(remaining, 1),
    }


async def list_eligible_recipients(
    session: AsyncSession,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Returns active, opted-in users eligible for direct messaging with 24h window badges."""
    # Active users
    user_stmt = (
        select(User)
        .where(
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
        .order_by(desc(User.created_at))
        .limit(limit)
    )
    users = (await session.execute(user_stmt)).scalars().all()

    recipients = []
    for u in users:
        # Check active consent
        consent_stmt = select(ConsentRecord).where(
            ConsentRecord.user_id == u.id,
            ConsentRecord.purpose == "birth_data_processing",
            ConsentRecord.granted == True,
            ConsentRecord.revoked_at.is_(None),
        )
        consent = (await session.execute(consent_stmt)).scalars().first()

        window_info = await get_recipient_window_status(session, u.id)

        try:
            phone_raw = u.get_decrypted_phone()
            masked_phone = mask_phone_number(phone_raw)
        except Exception:
            masked_phone = "•••• (encrypted)"

        recipients.append({
            "id": str(u.id),
            "whatsapp_name": u.whatsapp_name or "Unknown User",
            "masked_phone": masked_phone,
            "has_consent": consent is not None,
            "window_active": window_info["window_active"],
            "window_expires_at": window_info["window_expires_at"],
            "hours_remaining": window_info["hours_remaining"],
            "created_at": u.created_at.isoformat(),
        })

    return recipients


async def send_direct_user_message(
    session: AsyncSession,
    admin: AdminUser,
    user_id: uuid.UUID,
    message_text: str,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Sends a single direct WhatsApp message to an eligible user and tracks delivery status.

    Strictly complies with Meta policy: free-form text messages are rejected if outside the 24h window.
    """
    clean_text = message_text.strip()
    if not clean_text:
        raise ValueError("Message content cannot be empty.")

    # 1. Fetch user
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None or user.status != UserStatus.ACTIVE:
        raise ValueError("Recipient user not found, deleted, or inactive.")

    # 2. Check affirmative consent
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == user.id,
        ConsentRecord.purpose == "birth_data_processing",
        ConsentRecord.granted == True,
        ConsentRecord.revoked_at.is_(None),
    )
    consent = (await session.execute(consent_stmt)).scalars().first()
    if not consent:
        raise ValueError("Recipient has not granted active consent or has revoked data processing.")

    # 3. Check 24-hour Meta Customer Service Window (strict policy enforcement)
    window_info = await get_recipient_window_status(session, user.id)
    if not window_info["window_active"]:
        raise ValueError(
            "The 24-hour Meta Customer Service Window has expired for this user. "
            "Under Meta WhatsApp Cloud API policy, free-form text messages cannot be sent outside the 24-hour window. "
            "You must send an approved message template to re-engage this user."
        )

    # 4. Decrypt recipient phone number
    recipient_phone = user.get_decrypted_phone()

    # 5. Retrieve or create active Conversation
    conv_stmt = select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.status == ConversationStatus.ACTIVE,
    )
    conversation = (await session.execute(conv_stmt)).scalars().first()
    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            channel="whatsapp",
            status=ConversationStatus.ACTIVE,
            current_state=ConversationState.READING_READY,
            state_metadata={"created_by_admin": admin.username},
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    # 6. Record outbound ConversationMessage (pending until dispatch succeeds)
    out_msg = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        content_type="text",
        delivery_status="pending",
        status_timestamp=datetime.now(timezone.utc),
    )
    out_msg.set_content(clean_text)
    session.add(out_msg)
    await session.commit()

    # 7. Dispatch via WhatsApp Cloud API
    try:
        meta_response = await send_whatsapp_text(to_phone=recipient_phone, text_body=clean_text)
        wamid = None
        if isinstance(meta_response, dict) and meta_response.get("messages"):
            wamid = meta_response["messages"][0].get("id")

        out_msg.delivery_status = "sent"
        out_msg.status_timestamp = datetime.now(timezone.utc)
        if wamid:
            out_msg.whatsapp_message_id = wamid
        await session.commit()
    except Exception as exc:
        out_msg.delivery_status = "failed"
        out_msg.status_timestamp = datetime.now(timezone.utc)
        out_msg.error_message = str(exc)
        await session.commit()
        logger.error("Failed to deliver direct WhatsApp message to user %s: %s", user.id, exc)
        raise

    # 8. Immutable security audit event
    audit = AuditEvent(
        actor_id=str(admin.id),
        actor_role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
        action="DIRECT_MESSAGE_SENT",
        target_entity="user",
        target_id=str(user.id),
        details={
            "whatsapp_message_id": wamid,
            "char_count": len(clean_text),
            "window_active": True,
        },
        ip_address=ip_address,
    )
    session.add(audit)
    await session.commit()

    logger.info("Admin %s sent direct message to user %s (wamid=%s)", admin.username, user.id, wamid)
    return {
        "status": "success",
        "message_id": str(out_msg.id),
        "whatsapp_message_id": wamid,
        "delivery_status": out_msg.delivery_status,
        "recipient_masked": mask_phone_number(recipient_phone),
        "meta_response": meta_response,
    }


async def send_direct_template_message(
    session: AsyncSession,
    admin: AdminUser,
    user_id: uuid.UUID,
    template_name: str,
    language_code: str = "en",
    body_parameters: Optional[List[str]] = None,
    header_parameters: Optional[List[str]] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Sends an approved Meta WhatsApp Message Template to an eligible user (compliant outside 24h window)."""
    validate_template_name(template_name)
    params = body_parameters or []

    # 1. Fetch user
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None or user.status != UserStatus.ACTIVE:
        raise ValueError("Recipient user not found, deleted, or inactive.")

    # 2. Check affirmative consent
    consent_stmt = select(ConsentRecord).where(
        ConsentRecord.user_id == user.id,
        ConsentRecord.purpose == "birth_data_processing",
        ConsentRecord.granted == True,
        ConsentRecord.revoked_at.is_(None),
    )
    consent = (await session.execute(consent_stmt)).scalars().first()
    if not consent:
        raise ValueError("Recipient has not granted active consent or has revoked data processing.")

    # 3. Decrypt recipient phone number
    recipient_phone = user.get_decrypted_phone()

    # 4. Retrieve or create active Conversation
    conv_stmt = select(Conversation).where(
        Conversation.user_id == user.id,
        Conversation.status == ConversationStatus.ACTIVE,
    )
    conversation = (await session.execute(conv_stmt)).scalars().first()
    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            channel="whatsapp",
            status=ConversationStatus.ACTIVE,
            current_state=ConversationState.READING_READY,
            state_metadata={"created_by_admin": admin.username},
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

    # 5. Record outbound ConversationMessage (pending until dispatch succeeds)
    summary_text = f"Template: {template_name} | Lang: {language_code} | Params: {params}"
    out_msg = ConversationMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        direction=MessageDirection.OUTBOUND,
        sender=MessageSender.ASSISTANT,
        content_type="template",
        delivery_status="pending",
        status_timestamp=datetime.now(timezone.utc),
    )
    out_msg.set_content(summary_text)
    session.add(out_msg)
    await session.commit()

    # 6. Dispatch via WhatsApp Cloud API Templates
    try:
        meta_response = await send_whatsapp_template(
            to_phone=recipient_phone,
            template_name=template_name,
            language_code=language_code,
            body_parameters=params,
            header_parameters=header_parameters,
        )
        wamid = None
        if isinstance(meta_response, dict) and meta_response.get("messages"):
            wamid = meta_response["messages"][0].get("id")

        out_msg.delivery_status = "sent"
        out_msg.status_timestamp = datetime.now(timezone.utc)
        if wamid:
            out_msg.whatsapp_message_id = wamid
        await session.commit()
    except Exception as exc:
        out_msg.delivery_status = "failed"
        out_msg.status_timestamp = datetime.now(timezone.utc)
        out_msg.error_message = str(exc)
        await session.commit()
        logger.error("Failed to deliver WhatsApp template '%s' to user %s: %s", template_name, user.id, exc)
        raise

    # 7. Immutable security audit event
    audit = AuditEvent(
        actor_id=str(admin.id),
        actor_role=admin.role.value if hasattr(admin.role, "value") else str(admin.role),
        action="TEMPLATE_MESSAGE_SENT",
        target_entity="user",
        target_id=str(user.id),
        details={
            "template_name": template_name,
            "language_code": language_code,
            "params_count": len(params),
            "whatsapp_message_id": wamid,
        },
        ip_address=ip_address,
    )
    session.add(audit)
    await session.commit()

    logger.info("Admin %s sent template '%s' to user %s (wamid=%s)", admin.username, template_name, user.id, wamid)
    return {
        "status": "success",
        "message_id": str(out_msg.id),
        "whatsapp_message_id": wamid,
        "delivery_status": out_msg.delivery_status,
        "recipient_masked": mask_phone_number(recipient_phone),
        "meta_response": meta_response,
    }


async def get_recent_outbound_messages(
    session: AsyncSession,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Returns recent outbound messages with their current delivery status tracking."""
    stmt = (
        select(ConversationMessage, User)
        .join(User, ConversationMessage.user_id == User.id)
        .where(
            ConversationMessage.direction == MessageDirection.OUTBOUND,
        )
        .order_by(desc(ConversationMessage.created_at))
        .limit(limit)
    )
    results = (await session.execute(stmt)).all()

    items = []
    for msg, user in results:
        content_preview = ""
        try:
            content_preview = msg.get_content()
            if len(content_preview) > 120:
                content_preview = content_preview[:120] + "..."
        except Exception:
            content_preview = "(encrypted)"

        masked_phone = "••••"
        try:
            masked_phone = mask_phone_number(user.get_decrypted_phone())
        except Exception:
            pass

        items.append({
            "id": str(msg.id),
            "user_id": str(user.id),
            "whatsapp_name": user.whatsapp_name or "User",
            "masked_phone": masked_phone,
            "whatsapp_message_id": msg.whatsapp_message_id,
            "content_preview": content_preview,
            "delivery_status": msg.delivery_status or "sent",
            "status_timestamp": msg.status_timestamp.isoformat() if msg.status_timestamp else None,
            "error_code": msg.error_code,
            "error_message": msg.error_message,
            "created_at": msg.created_at.isoformat(),
        })

    return items
