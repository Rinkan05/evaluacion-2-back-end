"""Vistas HTML para catálogo, carro, autenticación y seguimiento de solicitudes."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    InstitutionCreationForm,
    ManagedUserCreationForm,
    ManagedUserUpdateForm,
    OrderStatusForm,
    SupplyForm,
)
from .models import Carro, CustomUser, Insumo, ItemCarro, Solicitud
from .permissions import is_warehouse_manager
from .services import (
    OrderRequestError,
    change_order_status,
    create_paid_order,
)


def is_medical_institution(user):
    """Separa a los clientes institucionales de las cuentas de bodega."""
    return user.is_authenticated and not is_warehouse_manager(user)


# CATÁLOGO HTML
# Consulta únicamente lotes no vencidos y con stock positivo, luego entrega
# esos objetos a la plantilla para formar las tarjetas visibles.
def pagina_inicio(request, **kwargs):
    """Renderiza el catálogo público con lotes disponibles y no vencidos."""
    supplies = Insumo.objects.select_related('category').filter(
        stock_boxes__gt=0,
        expiration_date__gte=timezone.localdate(),
    )
    return render(request, 'academic/inicio.html', {'supplies': supplies})


def quienes_somos(request):
    """Renderiza la página institucional informativa."""
    return render(request, 'academic/quienes_somos.html')


def servicios(request):
    """Renderiza el resumen de servicios de abastecimiento."""
    return render(request, 'academic/servicios.html')


def contacto(request):
    """Muestra el formulario de contacto y confirma el envío simulado."""
    if request.method == 'POST':
        messages.success(request, 'Tu mensaje fue recibido. Te contactaremos pronto.')
        return redirect('contacto')
    return render(request, 'academic/contacto.html')


def registrar_usuario(request):
    """Registra una nueva cuenta con el formulario estándar de Django."""
    if request.method == 'POST':
        form = InstitutionCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu cuenta de institución fue creada correctamente.')
            return redirect('inicio')
    else:
        form = InstitutionCreationForm()
    return render(request, 'academic/registro.html', {'form': form})


def iniciar_sesion(request):
    """Autentica al usuario y lo deriva a la sección que corresponde a su rol."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            # El personal va al panel; los clientes vuelven a su página solicitada.
            if is_warehouse_manager(request.user):
                return redirect('panel-personal')
            # Acepta solo destinos locales para evitar redirecciones a otros sitios.
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
    """Cierra la sesión web y devuelve al catálogo."""
    logout(request)
    return redirect('inicio')


@user_passes_test(is_warehouse_manager, login_url='acceso-superusuario')
def panel_personal(request):
    """Muestra accesos de trabajo solo al gestor o superusuario."""
    return render(request, 'academic/panel_personal.html')


@user_passes_test(is_warehouse_manager, login_url='acceso-superusuario')
def gestionar_interno(request):
    """Administra bodega con las mismas reglas de negocio que la API REST."""
    # La autorización del decorador protege GET y POST; solo el gestor de
    # bodega o el superusuario puede ver y ejecutar estas operaciones.
    create_form = SupplyForm()
    edit_forms = {}
    status_forms = {}

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create-supply':
            create_form = SupplyForm(request.POST)
            if create_form.is_valid():
                create_form.save()
                messages.success(request, 'El insumo fue agregado al inventario.')
                return redirect('gestion-interna')
        elif action == 'update-supply':
            supply = get_object_or_404(Insumo, pk=request.POST.get('supply_id'))
            form = SupplyForm(request.POST, instance=supply)
            if form.is_valid():
                form.save()
                messages.success(request, 'El insumo fue actualizado.')
                return redirect('gestion-interna')
            edit_forms[supply.pk] = form
        elif action == 'delete-supply':
            supply = get_object_or_404(Insumo, pk=request.POST.get('supply_id'))
            try:
                supply.delete()
            except ProtectedError:
                messages.error(
                    request,
                    'No se puede eliminar un insumo asociado a una solicitud.',
                )
            else:
                messages.success(request, 'El insumo fue eliminado.')
            return redirect('gestion-interna')
        elif action == 'update-order-status':
            form = OrderStatusForm(request.POST)
            if form.is_valid():
                try:
                    # La página no replica la lógica: usa el servicio atómico
                    # que también invoca PATCH /api/solicitudes/{id}/estado/.
                    order = change_order_status(
                        form.cleaned_data['order_id'],
                        form.cleaned_data['status'],
                    )
                except OrderRequestError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f'La solicitud #{order.pk} quedó '
                        f'{order.get_status_display().lower()}.',
                    )
                return redirect('gestion-interna')
            raw_order_id = request.POST.get('order_id', '')
            if raw_order_id.isdecimal():
                status_forms[int(raw_order_id)] = form
        else:
            messages.error(request, 'La acción de bodega no es válida.')
            return redirect('gestion-interna')

    supplies = list(
        Insumo.objects.select_related('category').order_by(
            'commercial_name',
            'lot_number',
        )
    )
    # Mantiene los formularios por objeto para mostrar errores de validación
    # junto al lote editado, sin perder los datos enviados.
    for supply in supplies:
        supply.edit_form = edit_forms.get(supply.pk, SupplyForm(instance=supply))

    orders = list(
        Solicitud.objects.select_related('user', 'dispatch')
        .prefetch_related('items')
        .order_by('-created_at', '-pk')
    )
    # Solo las solicitudes PAGADO muestran controles de entrega/cancelación;
    # el servicio vuelve a validar el estado para no confiar en la interfaz.
    for order in orders:
        order.status_form = status_forms.get(
            order.pk,
            OrderStatusForm(initial={'order_id': order.pk}),
        )

    return render(
        request,
        'academic/crud.html',
        {
            'create_form': create_form,
            'supplies': supplies,
            'orders': orders,
        },
    )


@login_required(login_url='iniciar-sesion')
def gestionar_usuarios(request):
    """Permite al superusuario maestro administrar cuentas desde el sitio."""
    if not request.user.is_superuser:
        return HttpResponseForbidden(
            'Solo el superusuario maestro puede gestionar usuarios.'
        )

    create_form = ManagedUserCreationForm()
    users = list(CustomUser.objects.order_by('username'))
    selected_user = None
    update_form = None
    selected_user_id = request.GET.get('usuario')
    if selected_user_id:
        selected_user = get_object_or_404(
            CustomUser,
            pk=selected_user_id,
            is_superuser=False,
        )
        if selected_user.pk != request.user.pk:
            update_form = ManagedUserUpdateForm(instance=selected_user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            create_form = ManagedUserCreationForm(request.POST)
            if create_form.is_valid():
                created_user = create_form.save()
                messages.success(request, 'La cuenta fue creada correctamente.')
                return redirect(
                    f'{reverse("gestionar-usuarios")}?usuario={created_user.pk}'
                )
        elif action in {'update', 'toggle-active'}:
            target_user = get_object_or_404(
                CustomUser,
                pk=request.POST.get('user_id'),
                is_superuser=False,
            )
            selected_user = target_user
            if target_user.pk == request.user.pk:
                messages.error(
                    request,
                    'No puedes cambiar el rol ni desactivar tu propia cuenta.',
                )
                return redirect('gestionar-usuarios')

            if action == 'toggle-active':
                target_user.is_active = not target_user.is_active
                target_user.save(update_fields=['is_active'])
                messages.success(
                    request,
                    'El estado de la cuenta fue actualizado.',
                )
                return redirect(
                    f'{reverse("gestionar-usuarios")}?usuario={target_user.pk}'
                )

            update_form = ManagedUserUpdateForm(request.POST, instance=target_user)
            if update_form.is_valid():
                update_form.save()
                messages.success(request, 'La cuenta fue actualizada correctamente.')
                return redirect(
                    f'{reverse("gestionar-usuarios")}?usuario={target_user.pk}'
                )
        else:
            messages.error(request, 'La acción de administración no es válida.')
            return redirect('gestionar-usuarios')
    else:
        create_form = ManagedUserCreationForm()

    return render(
        request,
        'academic/gestionar_usuarios.html',
        {
            'create_form': create_form,
            'users': users,
            'selected_user': selected_user,
            'update_form': update_form,
        },
    )


@login_required(login_url='iniciar-sesion')
@user_passes_test(is_medical_institution, login_url='iniciar-sesion')
def carrito(request):
    """Carga el carro del usuario desde PostgreSQL, sin depender de la sesión."""
    # El carro y sus líneas se guardan en la base; se calculan subtotales al leer.
    cart, _ = Carro.objects.get_or_create(user=request.user)
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
    # Rechaza lotes vencidos y cantidades inválidas antes de persistir el carro.
    supply = get_object_or_404(Insumo, pk=insumo_id)
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

    # Crear o actualizar evita duplicar el mismo producto dentro del carro.
    cart, _ = Carro.objects.get_or_create(user=request.user)
    ItemCarro.objects.update_or_create(
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
    """Actualiza cantidades o elimina líneas cuando la cantidad queda en cero."""
    cart, _ = Carro.objects.get_or_create(user=request.user)
    # Se procesa cada línea del usuario: cero quita el artículo; positivo actualiza.
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
    """Quita del carro propio el insumo indicado."""
    cart, _ = Carro.objects.get_or_create(user=request.user)
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
    """Lista el historial de solicitudes pertenecientes a la institución."""
    # El filtro por usuario evita exponer pedidos de otras instituciones.
    orders = (
        Solicitud.objects.filter(user=request.user)
        .prefetch_related('items', 'dispatch')
    )
    return render(request, 'academic/mis_solicitudes.html', {'orders': orders})
