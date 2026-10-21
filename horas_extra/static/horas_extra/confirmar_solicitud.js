// Antes de enviar la solicitud de hora extra se muestra una ventana para confirmar:
// solo se puede solicitar una vez por turno.
(function () {
    const formulario = document.getElementById('formulario-solicitud');
    const ventana = document.getElementById('confirmar-solicitud');
    let confirmada = false;

    function valor(nombre) {
        return formulario.querySelector('[name="' + nombre + '"]');
    }

    formulario.addEventListener('submit', function (evento) {
        if (confirmada) return;
        const desde = valor('hora_inicio').value;
        const hasta = valor('hora_fin').value;
        const administrador = valor('administrador');
        const motivo = valor('motivo').value.trim();
        // Si falta algo, se deja enviar para que el sistema muestre qué falta.
        if (!desde || !hasta || !motivo || !administrador.value) return;

        evento.preventDefault();
        document.getElementById('confirmar-desde').textContent = desde;
        document.getElementById('confirmar-hasta').textContent = hasta;
        document.getElementById('confirmar-total').textContent = document.getElementById('total-horas').textContent;
        document.getElementById('confirmar-administrador').textContent = administrador.selectedOptions[0].text;

        if (typeof ventana.showModal === 'function') {
            ventana.showModal();
        } else if (window.confirm('Solo se puede solicitar una vez la hora extra de este turno. ¿Desea enviarla?')) {
            confirmada = true;
            formulario.submit();
        }
    });

    document.getElementById('confirmar-enviar').addEventListener('click', function () {
        confirmada = true;
        this.disabled = true;
        ventana.close();
        formulario.submit();
    });

    document.getElementById('confirmar-revisar').addEventListener('click', function () {
        ventana.close();
    });
})();
