const API_BASE = "";
const salida = document.getElementById("salida");
const latInput = document.getElementById("latitud");
const lonInput = document.getElementById("longitud");
const altInput = document.getElementById("altitud");
const diasInput = document.getElementById("dias");
const fechaObjetivoInput = document.getElementById("fecha-objetivo");
const btnModoDias = document.getElementById("btn-modo-dias");
const btnModoFecha = document.getElementById("btn-modo-fecha");
let modoConsulta = "dias";
let graficaTemperatura = null;
let graficaLluvia = null;

const mapa = L.map("mapa").setView([13.79, -88.9], 8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(mapa);

let marcador = L.marker([parseFloat(latInput.value), parseFloat(lonInput.value)]).addTo(mapa);

mapa.on("click", (e) => {
  const { lat, lng } = e.latlng;
  latInput.value = lat.toFixed(4);
  lonInput.value = lng.toFixed(4);
  marcador.setLatLng([lat, lng]);
});

function diasHastaFecha(fechaIso) {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const fecha = new Date(`${fechaIso}T00:00:00`);
  const msPorDia = 1000 * 60 * 60 * 24;
  return Math.floor((fecha - hoy) / msPorDia);
}

function actualizarModoConsulta() {
  const esDias = modoConsulta === "dias";
  btnModoDias.classList.toggle("activo", esDias);
  btnModoFecha.classList.toggle("activo", !esDias);
  diasInput.disabled = !esDias;
  fechaObjetivoInput.disabled = esDias;
}

function payload() {
  const diasSolicitados = parseInt(diasInput.value, 10);
  let diasAplicados = Math.min(Math.max(diasSolicitados, 1), 16);
  const fechaObjetivo = modoConsulta === "fecha" ? fechaObjetivoInput.value : "";

  if (modoConsulta === "fecha") {
    if (!fechaObjetivo) {
      throw new Error("Selecciona una fecha exacta para consultar en modo calendario.");
    }
    const diferencia = diasHastaFecha(fechaObjetivo);
    if (diferencia < 0 || diferencia > 15) {
      throw new Error("Solo se puede pronosticar una fecha dentro de los próximos 16 días.");
    }
    diasAplicados = diferencia + 1;
  } else if (diasSolicitados > 16) {
    diasInput.value = "16";
    salida.innerHTML =
      '<p class="mensaje-aviso">Open-Meteo permite hasta 16 días. Se ajustó tu solicitud automáticamente a 16.</p>';
  }
  return {
    datos: {
      latitud: parseFloat(latInput.value),
      longitud: parseFloat(lonInput.value),
      altitud: parseFloat(altInput.value),
      dias: diasAplicados,
    },
    fechaObjetivo,
  };
}

function limpiarSalida() {
  if (graficaTemperatura) {
    graficaTemperatura.destroy();
    graficaTemperatura = null;
  }
  if (graficaLluvia) {
    graficaLluvia.destroy();
    graficaLluvia = null;
  }
  salida.innerHTML = "";
}

function renderUbicacion(ubicacion) {
  const bloque = document.createElement("div");
  bloque.className = "ubicacion";
  bloque.textContent = `Ubicación: lat ${ubicacion.latitud}, lon ${ubicacion.longitud}, alt ${ubicacion.altitud} m`;
  salida.appendChild(bloque);
}

function crearTarjeta(titulo) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "tarjeta-dia";
  const encabezado = document.createElement("h3");
  encabezado.innerHTML = titulo;
  tarjeta.appendChild(encabezado);
  return tarjeta;
}

function agregarLinea(tarjeta, texto) {
  const linea = document.createElement("p");
  linea.className = "linea-dato";
  linea.textContent = texto;
  tarjeta.appendChild(linea);
}

function iconoCondicion(lluviaMm) {
  if (lluviaMm >= 20) return "⛈️";
  if (lluviaMm >= 5) return "🌧️";
  return "☀️";
}

function agregarTemperaturaGrande(tarjeta, etiqueta, valor) {
  const bloque = document.createElement("div");
  bloque.className = "temperatura-grande";
  bloque.innerHTML = `<span class="etiqueta-temp">${etiqueta}</span><strong>${valor.toFixed(1)} °C</strong>`;
  tarjeta.appendChild(bloque);
}

function renderForecast(datos, fechaObjetivo = "") {
  limpiarSalida();
  renderUbicacion(datos.ubicacion);
  const lista = document.createElement("div");
  lista.className = "lista-tarjetas";
  const diasFiltrados = fechaObjetivo ? datos.dias.filter((dia) => dia.fecha === fechaObjetivo) : datos.dias;
  if (diasFiltrados.length === 0) {
    salida.innerHTML += '<p class="mensaje-aviso">La fecha seleccionada no está disponible en la respuesta.</p>';
    return;
  }
  diasFiltrados.forEach((dia) => {
    const icono = iconoCondicion(dia.lluvia_mm);
    const tarjeta = crearTarjeta(`${icono} Fecha: ${dia.fecha}`);
    const tempMedia = (dia.temperatura_max + dia.temperatura_min) / 2;
    agregarTemperaturaGrande(tarjeta, "Temperatura media", tempMedia);
    agregarLinea(tarjeta, `Temperatura max: ${dia.temperatura_max} °C`);
    agregarLinea(tarjeta, `Temperatura min: ${dia.temperatura_min} °C`);
    agregarLinea(tarjeta, `Lluvia pronóstico: ${dia.lluvia_mm} mm`);
    agregarLinea(tarjeta, `Humedad: ${dia.humedad_relativa}%`);
    lista.appendChild(tarjeta);
  });
  salida.appendChild(lista);
}

function renderAjustado(datos, fechaObjetivo = "") {
  limpiarSalida();
  renderUbicacion(datos.ubicacion);
  const lista = document.createElement("div");
  lista.className = "lista-tarjetas";
  const diasFiltrados = fechaObjetivo ? datos.dias.filter((dia) => dia.fecha === fechaObjetivo) : datos.dias;
  if (diasFiltrados.length === 0) {
    salida.innerHTML += '<p class="mensaje-aviso">La fecha seleccionada no está disponible en la respuesta.</p>';
    return;
  }
  diasFiltrados.forEach((dia) => {
    const icono = iconoCondicion(dia.lluvia_pronosticada_mm);
    const tarjeta = crearTarjeta(`${icono} Fecha: ${dia.fecha}`);
    agregarTemperaturaGrande(tarjeta, "Temperatura ajustada", dia.temperatura_ajustada);
    agregarLinea(tarjeta, `Temp pronosticada: ${dia.temperatura_pronosticada} °C`);
    agregarLinea(tarjeta, `Lluvia pronosticada: ${dia.lluvia_pronosticada_mm} mm`);
    agregarLinea(tarjeta, `Prob. lluvia ajustada: ${(dia.probabilidad_lluvia_ajustada * 100).toFixed(1)}%`);
    lista.appendChild(tarjeta);
  });
  salida.appendChild(lista);
}

function renderSiembra(datos, fechaObjetivo = "") {
  limpiarSalida();
  renderUbicacion(datos.ubicacion);
  const lista = document.createElement("div");
  lista.className = "lista-tarjetas";
  const diasFiltrados = fechaObjetivo
    ? datos.recomendaciones.filter((dia) => dia.fecha === fechaObjetivo)
    : datos.recomendaciones;
  if (diasFiltrados.length === 0) {
    salida.innerHTML += '<p class="mensaje-aviso">La fecha seleccionada no está disponible en la respuesta.</p>';
    return;
  }
  diasFiltrados.forEach((dia) => {
    const tarjeta = crearTarjeta(`🌱 Fecha: ${dia.fecha}`);
    const estado = document.createElement("span");
    estado.className = `estado-siembra ${dia.apto_siembra ? "apto" : "no-apto"}`;
    estado.textContent = dia.apto_siembra ? "Apto para sembrar" : "No apto para sembrar";
    tarjeta.appendChild(estado);
    agregarLinea(tarjeta, `Puntaje: ${dia.puntaje}`);
    agregarLinea(tarjeta, `Razón: ${dia.razon}`);
    lista.appendChild(tarjeta);
  });
  salida.appendChild(lista);
}

function renderInsights(datos) {
  limpiarSalida();
  renderUbicacion(datos.ubicacion);

  const region = document.createElement("p");
  region.className = "linea-dato";
  region.innerHTML = `<strong>Microclima regional:</strong> ${datos.region_microclima}`;
  salida.appendChild(region);

  const riesgos = document.createElement("div");
  riesgos.className = "lista-tarjetas";
  const tarjetaSequia = crearTarjeta("🌵 Riesgo de sequía");
  agregarLinea(tarjetaSequia, `Nivel: ${datos.riesgo_sequia.nivel}`);
  agregarLinea(tarjetaSequia, `Puntaje: ${datos.riesgo_sequia.puntaje}`);
  agregarLinea(tarjetaSequia, datos.riesgo_sequia.descripcion);
  riesgos.appendChild(tarjetaSequia);

  const tarjetaExceso = crearTarjeta("🌧️ Exceso de lluvia");
  agregarLinea(tarjetaExceso, `Nivel: ${datos.riesgo_exceso_lluvia.nivel}`);
  agregarLinea(tarjetaExceso, `Puntaje: ${datos.riesgo_exceso_lluvia.puntaje}`);
  agregarLinea(tarjetaExceso, datos.riesgo_exceso_lluvia.descripcion);
  riesgos.appendChild(tarjetaExceso);
  salida.appendChild(riesgos);

  const notiTitulo = document.createElement("h3");
  notiTitulo.textContent = "🔔 Notificaciones";
  salida.appendChild(notiTitulo);
  const listaNoti = document.createElement("ul");
  listaNoti.className = "lista-notificaciones";
  (datos.notificaciones || []).forEach((n) => {
    const li = document.createElement("li");
    li.textContent = n;
    listaNoti.appendChild(li);
  });
  if (!datos.notificaciones || datos.notificaciones.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Sin alertas críticas por ahora.";
    listaNoti.appendChild(li);
  }
  salida.appendChild(listaNoti);

  const comparacion = document.createElement("p");
  comparacion.className = "mensaje-aviso";
  comparacion.textContent = `Comparación anual lluvia: actual ${datos.comparacion_anual.total_actual_mm} mm vs anterior ${datos.comparacion_anual.total_anterior_mm} mm (variación ${datos.comparacion_anual.variacion_porcentual}%).`;
  salida.appendChild(comparacion);

  const canvasTemp = document.createElement("canvas");
  canvasTemp.id = "grafica-temperatura";
  canvasTemp.className = "grafica";
  salida.appendChild(canvasTemp);
  graficaTemperatura = new Chart(canvasTemp, {
    type: "line",
    data: {
      labels: datos.temperatura_proximos_dias.map((d) => d.fecha),
      datasets: [
        {
          label: "Temperatura ajustada (°C)",
          data: datos.temperatura_proximos_dias.map((d) => d.temperatura_c),
          borderColor: "#1c84dd",
          backgroundColor: "rgba(28, 132, 221, 0.2)",
          tension: 0.25,
        },
      ],
    },
  });

  const canvasLluvia = document.createElement("canvas");
  canvasLluvia.id = "grafica-lluvia";
  canvasLluvia.className = "grafica";
  salida.appendChild(canvasLluvia);
  graficaLluvia = new Chart(canvasLluvia, {
    type: "bar",
    data: {
      labels: datos.lluvia_mensual_actual.map((d) => d.mes),
      datasets: [
        {
          label: "Lluvia mes actual (mm)",
          data: datos.lluvia_mensual_actual.map((d) => d.lluvia_mm),
          backgroundColor: "rgba(24, 133, 222, 0.7)",
        },
        {
          label: "Lluvia año anterior (mm)",
          data: datos.lluvia_mensual_anterior.map((d) => d.lluvia_mm),
          backgroundColor: "rgba(112, 176, 229, 0.7)",
        },
      ],
    },
  });
}

async function consultar(endpoint) {
  salida.innerHTML = '<p class="mensaje-inicial">Consultando API...</p>';
  try {
    const solicitud = payload();
    const respuesta = await fetch(`${API_BASE}/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(solicitud.datos),
    });
    if (!respuesta.ok) {
      throw new Error(await respuesta.text());
    }
    const datos = await respuesta.json();
    if (endpoint === "forecast") {
      renderForecast(datos, solicitud.fechaObjetivo);
      return;
    }
    if (endpoint === "adjusted") {
      renderAjustado(datos, solicitud.fechaObjetivo);
      return;
    }
    if (endpoint === "planting") {
      renderSiembra(datos, solicitud.fechaObjetivo);
      return;
    }
    if (endpoint === "insights") {
      renderInsights(datos);
      return;
    }
    salida.innerHTML = '<p class="mensaje-inicial">No hay render definido para este endpoint.</p>';
  } catch (error) {
    salida.innerHTML = `<p class="mensaje-inicial">Error: ${error.message}</p>`;
  }
}

document.getElementById("btn-forecast").addEventListener("click", () => consultar("forecast"));
document.getElementById("btn-adjusted").addEventListener("click", () => consultar("adjusted"));
document.getElementById("btn-planting").addEventListener("click", () => consultar("planting"));
document.getElementById("btn-insights").addEventListener("click", () => consultar("insights"));
btnModoDias.addEventListener("click", () => {
  modoConsulta = "dias";
  actualizarModoConsulta();
});
btnModoFecha.addEventListener("click", () => {
  modoConsulta = "fecha";
  actualizarModoConsulta();
});
actualizarModoConsulta();
