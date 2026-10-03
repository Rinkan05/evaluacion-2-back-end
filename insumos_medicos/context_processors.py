"""Datos comunes inyectados en todas las plantillas HTML."""


def cart_context(request):
    """Comparte con la navegación el total de cajas del carro persistido."""
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
    """Lee nombre y sección de settings para que base.html los muestre."""
    from django.conf import settings

    return {
        'student_name': settings.STUDENT_NAME,
        'course_section': settings.COURSE_SECTION,
    }
