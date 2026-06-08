import logging
from django.db.models import Q
from ..models import CustomUser

logger = logging.getLogger(__name__)

def user_exists(username: str = None, email: str = None, phone_number: str = None) -> bool:
    """Return True if a non‑rejected user with any of the given identifiers exists.

    Args:
        username: Optional username to check.
        email: Optional email to check.
        phone_number: Optional phone number to check.

    The function ignores users whose status is 'REJECTED' so that re‑applications are allowed.
    """
    if not any([username, email, phone_number]):
        logger.warning("user_exists called without any identifier")
        return False
    query = Q()
    if username:
        query |= Q(username__iexact=username)
    if email:
        query |= Q(email__iexact=email)
    if phone_number:
        query |= Q(phone_number=phone_number)
    # Exclude rejected accounts – they can re‑apply.
    exists = CustomUser.objects.filter(query).exclude(status='REJECTED').exists()
    logger.debug(
        "User existence check – username=%s, email=%s, phone=%s → %s",
        username,
        email,
        phone_number,
        exists,
    )
    return exists
