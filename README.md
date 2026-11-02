# Gestor de gastos

Programa de escritorio para llevar las finanzas personales, hecho con **Python, Flask, SQLite y pywebview**. Se abre en su propia ventana (no en el navegador) y funciona sin internet. Tiene tres secciones:

| Sección | Qué hace |
|---|---|
| **Movimientos** | Registra ingresos y egresos por categoría, con balance mensual y saldo total. La tabla se ordena por fecha, categoría o monto. |
| **Crédito** | Un panel con el total de tus créditos, el calendario de cuotas de los próximos 12 meses y en qué categorías usas las tarjetas. Varias tarjetas o líneas de crédito (ej. Falabella, BCI), cada una con su cupo, compras en cuotas con interés y pagos. Soporta compras internacionales en dólares con cupo propio. Calcula deuda, cupo disponible y la próxima cuota estimada. |
| **Ahorro** | Registra depósitos y retiros, con una meta de ahorro. Los intereses se pueden sumar solos cada día o cada mes. |

Además, una página de **Resumen** junta lo más importante de cada mes (con flechas para revisar meses anteriores) y permite **exportar todo a Excel**.

![Resumen](docs/resumen.png)

<details>
<summary>Más capturas</summary>

![Movimientos](docs/movimientos.png)
![Panel de créditos](docs/credito.png)
![Detalle de un crédito](docs/credito-cuenta.png)
![Ahorro](docs/ahorro.png)

</details>

> Las capturas usan datos ficticios (`python main.py --demo`).

## Características

- Montos en pesos chilenos (`$15.000`); acepta escribir `15000`, `15.000` o `$15.000`.
- Exportación a Excel (.xlsx) con una hoja por sección, fechas y montos con formato.
- Sincronización entre computadores: elige en ⚙️ Ajustes una carpeta de OneDrive o Google Drive y la app guarda ahí tus datos. Avisa si la app está abierta en otro computador y si la nube creó copias en conflicto.
- Respaldo completo en ⚙️ Ajustes: exporta todos tus datos (incluidos color y fondo) a un `.zip` e impórtalos en otro computador. Antes de importar se guarda una copia automática de lo que tenías.
- Navegación por mes en los movimientos; clic en Fecha, Categoría o Monto para ordenar (y otra vez para invertir). El formulario recuerda el último tipo y fecha usados.
- Compras en hasta 48 cuotas con interés mensual opcional (cuota fija, sistema francés). Muestra cuántas cuotas van cobradas y cuánto se paga en intereses.
- Cupo internacional en dólares por tarjeta: compras y pagos en US$ por separado de los pesos, como en el estado de cuenta del banco. Al pagar dólares puedes anotar cuántos pesos costó.
- Tasa anual de ahorro: puedes escribirla o calcularla con lo que te paga el banco (ej. "$15 al día"). Los intereses se suman solos cada día o cada mes, sin perder decimales por redondeo.
- Pagos de tarjeta y depósitos de ahorro pueden reflejarse automáticamente como movimientos de la cuenta; si los borras, el movimiento vinculado también se borra.
- Validaciones: no deja pagar más que la deuda ni retirar más de lo ahorrado.
- Funciona sin internet; los datos nunca salen de tu computador.
- Personalización en ⚙️ Ajustes: color de botones y barras (8 colores listos o cualquier otro; los tonos del texto se ajustan solos para que siempre se lea bien) y fondo de pantalla con difuminado ajustable. La imagen se guarda junto a tus datos, fuera del proyecto.
- Tema claro, oscuro o automático (sigue a Windows), a elección en ⚙️ Ajustes. Los gráficos se dibujan con HTML y CSS, sin librerías externas.
- Tests con `pytest` y GitHub Actions; cada versión nueva genera y publica el `.exe` automáticamente.

## Descargar

La forma más fácil: baja **GestorGastos.exe** desde la [última versión](https://github.com/Daijinn-BKR/gestor-gastos/releases/latest) y ábrelo con doble clic (Windows 10/11). No necesitas instalar Python.

## Instalación (desde el código)

Requiere Python 3.10 o superior. En Windows 10/11 no necesitas nada más (usa Microsoft Edge WebView2, que viene incluido).

```bash
git clone https://github.com/Daijinn-BKR/gestor-gastos.git
cd gestor-gastos

python -m venv venv
# Windows:      venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

pip install -r requirements.txt
```

## Uso

```bash
python main.py           # abre la app con tus datos
python main.py --demo    # abre la app con datos ficticios, en una base aparte
```

## Crear el ejecutable (.exe)

Para abrir la app con doble clic, sin tener Python instalado:

```bash
pip install -r requirements-dev.txt
python build.py
```

El programa queda en `dist/GestorGastos.exe`. Puedes moverlo a donde quieras o crear un acceso directo en el escritorio. El ejecutable se genera para el sistema donde corres el script (en Windows sale un `.exe`).

> En la primera ejecución, Windows SmartScreen puede mostrar un aviso porque el programa no está firmado. Haz clic en *Más información → Ejecutar de todas formas*.

### Publicar una nueva versión

GitHub Actions genera el `.exe` solo. Basta con crear un tag que empiece con `v` y subirlo:

```bash
git tag v1.1.0
git push origin v1.1.0
```

El workflow `.github/workflows/release.yml` corre los tests en Windows, construye `GestorGastos.exe` y lo publica en Releases. Si algún test falla, no se publica nada.

## ¿Dónde se guardan mis datos?

En una carpeta de tu usuario, **fuera del proyecto**, así que es imposible subirlos a GitHub por error:

| Sistema | Carpeta |
|---|---|
| Windows | `%APPDATA%\GestorGastos\gastos.db` |
| macOS | `~/Library/Application Support/GestorGastos/gastos.db` |
| Linux | `~/.local/share/GestorGastos/gastos.db` |

Para respaldar tus datos usa **⚙️ Ajustes → Tus datos → Exportar mis datos**, o copia ese archivo. El modo demo usa `demo.db` en la misma carpeta.

### Usar la app en varios computadores

En **⚙️ Ajustes → Sincronizar entre computadores** puedes elegir una carpeta de OneDrive o Google Drive. La app copia ahí tus datos y desde entonces los guarda en esa carpeta. En el otro computador eliges la misma carpeta y presionas *Usar los datos de esa carpeta*. La ubicación elegida se recuerda en `ubicacion.json`, dentro de la carpeta de datos de cada computador.

Usa la app en un solo computador a la vez: SQLite no está pensado para que dos equipos escriban el mismo archivo al mismo tiempo, y la nube crearía copias en conflicto.

Cuando una nueva versión cambia la estructura de la base de datos, la app guarda antes una copia automática (`gastos.respaldo-FECHA.db`) y luego actualiza tus datos.

### Modo desarrollo

Como la interfaz está hecha con Flask, también puedes abrirla en el navegador mientras programas (con recarga automática):

```bash
flask --app gestor run --debug
```

## Tests

```bash
pytest -v
```

Cada test usa una base temporal, así que no afecta tus datos.

## Estructura

```
gestor-gastos/
├── main.py              # abre la app en una ventana de escritorio
├── build.py             # genera el ejecutable con PyInstaller
├── .github/workflows/   # tests en cada push y .exe automático en cada versión
├── gestor/
│   ├── __init__.py      # crea la app Flask
│   ├── rutas.py         # carpeta de datos según el sistema operativo
│   ├── db.py            # conexión SQLite, migraciones y comandos init-db / seed
│   ├── schema.sql       # tablas
│   ├── calculos.py      # cuotas, intereses, deuda y tasas (sin base de datos)
│   ├── exportar.py      # genera el archivo Excel
│   ├── respaldo.py      # exportar/importar todos los datos (.zip)
│   ├── ubicacion.py     # carpeta de datos elegida y avisos de sincronización
│   ├── colores.py       # color de acento y sus tonos legibles
│   ├── utils.py         # formato de pesos, validaciones
│   ├── seed.py          # datos ficticios
│   ├── views/           # una ruta por sección
│   ├── templates/       # HTML (Jinja2)
│   └── static/          # CSS
├── tests/
├── docs/                # capturas para este README
├── requirements.txt
└── requirements-dev.txt
```

## Ideas para seguir

- Editar registros (hoy solo se agregan y eliminan).
- Gráfico de evolución mensual.
- Varias metas de ahorro.
- Presupuesto por categoría con alertas.

## Licencia

MIT
