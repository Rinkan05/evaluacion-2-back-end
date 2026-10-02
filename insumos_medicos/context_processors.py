def cart_context(request):
    if not request.user.is_authenticated:
        return {'cart_count': 0}
    cart = getattr(request.user, 'cart', None)
    if cart is None:
        return {'cart_count': 0}
    return {
        'cart_count': sum(
            cart.items.values_list('quantity_boxes', flat=True)
        )
    }


def student_footer(request):
    """Provides required student attribution to every project HTML template."""
    from django.conf import settings

    return {
        'student_name': settings.STUDENT_NAME,
        'course_section': settings.COURSE_SECTION,
    }
