"""Vistas HTML para catálogo, carro, autenticación y seguimiento de solicitudes."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Cart, CartItem, Order, Supply
from .permissions import is_warehouse_manager
from .services import OrderRequestError, create_paid_order


def is_medical_institution(user):
    """Separa a los clientes institucionales de las cuentas de bodega."""
    return user.is_authenticated and not is_warehouse_manager(user)


# El catálogo solo muestra lotes vigentes y con existencias disponibles.
def pagina_inicio(request, **kwargs):
    supplies = Supply.objects.select_related('category').filter(
        stock_boxes__gt=0,
        expiration_date__gte=timezone.localdate(),
    )
    return render(request, 'academic/inicio.html', {'supplies': supplies})


def quienes_somos(request):
    return render(request, 'academic/quienes_somos.html')


def servicios(request):
    return render(request, 'academic/servicios.html')


def contacto(request):
    if request.method == 'POST':
        messages.success(request, 'Tu mensaje fue recibido. Te contactaremos pronto.')
        return redirect('contacto')
    return render(request, 'academic/contacto.html')


def registrar_usuario(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu cuenta de institución fue creada correctamente.')
            return redirect('inicio')
    else:
        form = UserCreationForm()
    return render(request, 'academic/registro.html', {'form': form})


def iniciar_sesion(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            if is_warehouse_manager(request.user):
                return redirect('panel-personal')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect('inicio')
    else:
        form = AuthenticationForm()
    return render(
        request,
        'academic/acceso_superusuario.html',
        {'form': form, 'next_url': next_url},
    )


def cerrar_sesion(request):
    logout(request)
    return redirect('inicio')


@user_passes_test(is_warehouse_manager, login_url='acceso-superusuario')
def panel_personal(request):
    return render(request, 'academic/panel_personal.html')


@user_passes_test(is_warehouse_manager, login_url='acceso-superusuario')
def gestionar_interno(request):
    return render(request, 'academic/crud.html')


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
def carrito(request):
    """Carga el carro del usuario desde PostgreSQL, sin depender de la sesión."""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related('supply__category')
    items = [
        {
            'id': item.pk,
            'supply': item.supply,
            'quantity': item.quantity_boxes,
            'subtotal': item.supply.price_per_box * item.quantity_boxes,
        }
        for item in cart_items
    ]
    total = sum((item['subtotal'] for item in items), start=0)
    return render(request, 'academic/carrito.html', {'items': items, 'total': total})


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
@require_POST
def agregar_carrito(request, insumo_id):
    """Actualiza el carro sin reservar ni descontar stock."""
    supply = get_object_or_404(Supply, pk=insumo_id)
    if supply.expiration_date < timezone.localdate():
        messages.error(request, 'No se puede solicitar un lote vencido.')
        return redirect(request.POST.get('next', 'inicio'))
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1:
        messages.error(request, 'La cantidad debe ser al menos una caja.')
        return redirect(request.POST.get('next', 'inicio'))

    cart, _ = Cart.objects.get_or_create(user=request.user)
    CartItem.objects.update_or_create(
        cart=cart,
        supply=supply,
        defaults={'quantity_boxes': quantity},
    )
    messages.success(request, f'{supply.commercial_name} se añadió al carro.')
    return redirect(request.POST.get('next', 'inicio'))


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
@require_POST
def actualizar_carrito(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    for item in cart.items.all():
        try:
            quantity = int(request.POST.get(f'quantity_{item.pk}', 0))
        except (TypeError, ValueError):
            messages.error(
                request,
                f'La cantidad de {item.supply.commercial_name} no es válida.',
            )
            return redirect('carrito')
        if quantity < 0:
            messages.error(
                request,
                f'La cantidad de {item.supply.commercial_name} no puede ser negativa.',
            )
            return redirect('carrito')
        if quantity < 1:
            item.delete()
        else:
            item.quantity_boxes = quantity
            item.save(update_fields=['quantity_boxes'])
    messages.success(request, 'Carro actualizado.')
    return redirect('carrito')


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
@require_POST
def eliminar_del_carrito(request, insumo_id):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart.items.filter(supply_id=insumo_id).delete()
    return redirect('carrito')


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
@require_POST
def finalizar_compra(request):
    """Delega la validación de stock y el checkout atómico al servicio de órdenes."""
    try:
        order = create_paid_order(request.user)
    except OrderRequestError as exc:
        messages.error(request, str(exc))
        return redirect('carrito')
    messages.success(request, f'Solicitud #{order.pk} pagada y enviada a despacho.')
    return redirect('mis-solicitudes')


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
def mis_solicitudes(request):
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related('items', 'dispatch')
    )
    return render(request, 'academic/mis_solicitudes.html', {'orders': orders})
