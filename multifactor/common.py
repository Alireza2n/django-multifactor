import logging
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render as dj_render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

import random

from .app_settings import mf_settings
from .models import UserKey, DisabledFallback

logger = logging.getLogger(__name__)


def has_multifactor(request):
    return UserKey.objects.filter(user=request.user, enabled=True).exists()


def active_factors(request):
    # automatically expire old factors
    now = timezone.now().timestamp()
    factors = request.session["multifactor"] = [
        *filter(
            lambda tup: tup[3] == False or tup[3] > now,
            request.session.get('multifactor', [])
        ),
    ]
    return factors


def disabled_fallbacks(request):
    return DisabledFallback.objects.filter(user=request.user).values_list('fallback', flat=True)


def next_check():
    return timezone.now().timestamp() + random.randint(
        mf_settings['RECHECK_MIN'],
        mf_settings['RECHECK_MAX']
    )


def render(request, template_name, context, **kwargs):
    return dj_render(request, template_name, {
        **context
    }, **kwargs)


def method_url(method):
    return f'multifactor:{method.lower()}_auth'


def write_session(request, key):
    """Write the multifactor session with the verified key"""
    request.session["multifactor"] = [
        (
            key.key_type if key else None,
            key.id if key else None,
            timezone.now().timestamp(),
            next_check() if mf_settings["RECHECK"] else False
        ),
        *filter(
            lambda tup: not key or tup[1] != key.id,
            request.session.get('multifactor', [])
        ),
    ]

    if key:
        key.last_used = timezone.now()
        key.save()


def login(request):
    if mf_settings['SHOW_LOGIN_MESSAGE']:
        messages.info(request, format_html(mf_settings['LOGIN_MESSAGE'], reverse('multifactor:home')))

    if 'multifactor-next' in request.session:
        return redirect(request.session.pop('multifactor-next', 'multifactor:home'))

    callback = mf_settings['LOGIN_CALLBACK']
    if callback:
        callable_func = import_string(callback)
        return callable_func(request, username=request.session["base_username"])

    # punch back to the login URL and let it decide what to do with you
    return redirect(settings.LOGIN_URL)


def is_mf_disabled():
    is_disabled = all((mf_settings['DISABLE'] is True, settings.DEBUG is True))
    if is_disabled is True:
        logger.warning(f'MULTIFACTOR.DISABLE and DEBUG are True, skipping MultiFactor protection.')
        return is_disabled
    return False
