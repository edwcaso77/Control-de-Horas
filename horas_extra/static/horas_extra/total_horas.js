// Muestra el total de horas entre «desde» y «hasta» mientras se escriben (si «hasta» es menor, termina al día siguiente).
(function () {
    const desde = document.querySelector('input[name="hora_inicio"]');
    const hasta = document.querySelector('input[name="hora_fin"]');
    const total = document.getElementById('total-horas');

    function minutos(valor) {
        const [h, m] = valor.split(':').map(Number);
        return h * 60 + m;
    }

    function actualizar() {
        if (!desde.value || !hasta.value) { total.textContent = '—'; return; }
        let diferencia = minutos(hasta.value) - minutos(desde.value);
        if (diferencia <= 0) diferencia += 24 * 60;
        const horas = Math.round(diferencia / 60 * 100) / 100;
        total.textContent = horas.toLocaleString('es-CO') + (horas === 1 ? ' hora' : ' horas');
    }

    desde.addEventListener('input', actualizar);
    hasta.addEventListener('input', actualizar);
    actualizar();
})();
