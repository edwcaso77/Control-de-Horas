from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import importar
from .forms import FuncionarioForm, catalogo_form
from .models import Area, Cargo, Funcionario
from .permisos import administrador_requerido

CATALOGOS = {
    'cargos': Cargo,
    'areas': Area,
}


@administrador_requerido
def lista(request):
    funcionarios = Funcionario.objects.select_related('usuario', 'cargo', 'area')

    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        funcionarios = funcionarios.filter(
            Q(nombres__icontains=busqueda)
            | Q(apellidos__icontains=busqueda)
            | Q(numero_documento__icontains=busqueda)
        )

    area = request.GET.get('area', '')
    if area.isdigit():
        funcionarios = funcionarios.filter(area_id=area)

    estado = request.GET.get('estado', 'activos')
    if estado == 'activos':
        funcionarios = funcionarios.filter(usuario__is_active=True)
    elif estado == 'inactivos':
        funcionarios = funcionarios.filter(usuario__is_active=False)

    return render(request, 'funcionarios/lista.html', {
        'funcionarios': funcionarios,
        'areas': Area.objects.all(),
        'busqueda': busqueda,
        'area': area,
        'estado': estado,
    })


@administrador_requerido
def crear(request):
    form = FuncionarioForm(request.POST or None, usuario_actual=request.user)
    if form.is_valid():
        funcionario = form.save()
        messages.success(request, f'Funcionario {funcionario} registrado. Usuario: {funcionario.numero_documento}')
        return redirect('funcionarios:lista')
    return render(request, 'funcionarios/formulario.html', {'form': form, 'titulo': 'Nuevo funcionario'})


@administrador_requerido
def editar(request, pk):
    funcionario = get_object_or_404(Funcionario, pk=pk)
    form = FuncionarioForm(request.POST or None, instance=funcionario, usuario_actual=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, f'Datos de {funcionario} actualizados.')
        return redirect('funcionarios:lista')
    return render(request, 'funcionarios/formulario.html', {
        'form': form,
        'titulo': f'Editar: {funcionario}',
        'funcionario': funcionario,
    })


@require_POST
@administrador_requerido
def cambiar_estado(request, pk):
    funcionario = get_object_or_404(Funcionario.objects.select_related('usuario'), pk=pk)
    usuario = funcionario.usuario
    if usuario == request.user:
        messages.error(request, 'No puede desactivar su propia cuenta.')
    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])
        estado = 'activado' if usuario.is_active else 'desactivado'
        messages.success(request, f'{funcionario} {estado}.')
    # Vuelve al listado conservando los filtros, solo si la dirección es de este mismo sitio.
    siguiente = request.POST.get('siguiente', '')
    if url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        return redirect(siguiente)
    return redirect('funcionarios:lista')


def _modelo_catalogo(tipo):
    try:
        return CATALOGOS[tipo]
    except KeyError:
        raise Http404


@administrador_requerido
def catalogo(request, tipo):
    modelo = _modelo_catalogo(tipo)
    form = catalogo_form(modelo)(request.POST or None)
    if form.is_valid():
        elemento = form.save()
        messages.success(request, f'«{elemento}» agregado.')
        return redirect('funcionarios:catalogo', tipo=tipo)
    return render(request, 'funcionarios/catalogo.html', {
        'tipo': tipo,
        'modelo': modelo._meta,
        'elementos': modelo.objects.all(),
        'form': form,
    })


@administrador_requerido
def catalogo_editar(request, tipo, pk):
    modelo = _modelo_catalogo(tipo)
    elemento = get_object_or_404(modelo, pk=pk)
    form = catalogo_form(modelo)(request.POST or None, instance=elemento)
    if form.is_valid():
        form.save()
        messages.success(request, f'«{elemento}» actualizado.')
        return redirect('funcionarios:catalogo', tipo=tipo)
    return render(request, 'funcionarios/catalogo_editar.html', {
        'tipo': tipo,
        'modelo': modelo._meta,
        'elemento': elemento,
        'form': form,
    })


@require_POST
@administrador_requerido
def catalogo_estado(request, tipo, pk):
    elemento = get_object_or_404(_modelo_catalogo(tipo), pk=pk)
    elemento.activo = not elemento.activo
    elemento.save(update_fields=['activo'])
    messages.success(request, f'«{elemento}» {"activado" if elemento.activo else "desactivado"}.')
    return redirect('funcionarios:catalogo', tipo=tipo)


CREDENCIALES_SESION = 'credenciales_importadas'
TIPO_EXCEL = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@administrador_requerido
def plantilla(request):
    """Descarga la plantilla de Excel para cargar funcionarios."""
    respuesta = HttpResponse(importar.plantilla_excel(), content_type=TIPO_EXCEL)
    respuesta['Content-Disposition'] = 'attachment; filename="plantilla_funcionarios.xlsx"'
    return respuesta


@administrador_requerido
def importar_excel(request):
    """Sube la plantilla llena y crea los funcionarios. Si una fila tiene errores, no se crea ninguno."""
    contexto = {}
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if archivo is None:
            contexto['error_archivo'] = 'Elija el archivo de Excel.'
        elif not archivo.name.lower().endswith('.xlsx'):
            contexto['error_archivo'] = 'El archivo debe ser de Excel (.xlsx).'
        elif archivo.size > 5 * 1024 * 1024:
            contexto['error_archivo'] = 'El archivo es demasiado grande (máximo 5 MB).'
        else:
            try:
                creados, errores, nuevos = importar.importar(archivo)
            except importar.ErrorDeArchivo as error:
                contexto['error_archivo'] = str(error)
            else:
                if errores:
                    contexto['errores'] = errores
                else:
                    credenciales = [(f.numero_documento, f.nombre_completo, clave) for f, clave in creados]
                    # Las contraseñas se pueden descargar una sola vez; luego se borran de la sesión.
                    request.session[CREDENCIALES_SESION] = credenciales
                    return render(request, 'funcionarios/importar_resultado.html', {
                        'credenciales': credenciales,
                        'nuevos': nuevos,
                    })
    return render(request, 'funcionarios/importar.html', contexto)


@administrador_requerido
def credenciales(request):
    """Descarga (una sola vez) las contraseñas iniciales de la última importación."""
    datos = request.session.pop(CREDENCIALES_SESION, None)
    if not datos:
        messages.error(request, 'Las contraseñas iniciales ya se descargaron o expiraron.')
        return redirect('funcionarios:lista')
    respuesta = HttpResponse(importar.credenciales_excel(datos), content_type=TIPO_EXCEL)
    respuesta['Content-Disposition'] = 'attachment; filename="contrasenas_iniciales.xlsx"'
    return respuesta
