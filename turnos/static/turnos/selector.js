// Selectores de turno de las pantallas de asignación (un día y varios días).
// Cada selector pinta el color de su turno y muestra la casilla de horas cuando el turno es de horas variables,
// y la de hora de inicio cuando además la pide (extramural).
(function () {
    function preparar(selector) {
        const opcion = selector.selectedOptions[0];
        const horas = selector.parentElement.querySelector('.horas-turno');
        const inicio = selector.parentElement.querySelector('.inicio-turno');

        selector.style.background = opcion && opcion.dataset.color ? opcion.dataset.color : '';
        selector.style.color = opcion && opcion.dataset.texto ? opcion.dataset.texto : '';
        selector.classList.toggle('turno-vacio', !selector.value);

        const variable = !!(opcion && opcion.hasAttribute('data-variable'));
        horas.hidden = !variable;
        horas.required = variable;
        if (variable) {
            horas.min = opcion.dataset.min;
            horas.max = opcion.dataset.max;
            if (!horas.value) horas.value = opcion.dataset.min;
        }

        const pideInicio = !!(opcion && opcion.hasAttribute('data-inicio'));
        inicio.hidden = !pideInicio;
        inicio.required = pideInicio;
    }

    function elegir(selector, valor) {
        selector.value = valor;
        preparar(selector);
    }

    document.querySelectorAll('.selector-turno').forEach(selector => {
        preparar(selector);
        selector.addEventListener('change', () => preparar(selector));
    });

    // Atajos: «Asignar a todos» y «Todos…» de cada columna cambian el turno principal de las celdas.
    document.querySelectorAll('.llenar').forEach(atajo => {
        atajo.addEventListener('change', () => {
            if (atajo.value === '*') return;
            const columna = atajo.dataset.columna;
            document.querySelectorAll('.selector-turno[data-ranura="1"]').forEach(selector => {
                if (columna === 'todas' || selector.dataset.columna === columna) elegir(selector, atajo.value);
            });
            atajo.value = '*';
        });
    });
})();
