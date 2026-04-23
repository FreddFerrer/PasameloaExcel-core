![PasameloaExcel](./docs/branding/header-brandmark-v2.png)


# PasameloaExcel

PasameloaExcel nace de un dolor real: cuando te llegan extractos bancarios en PDF y hay que pasarlos a Excel para trabajar, controlar, conciliar o presentar.

La idea es simple: subir el PDF, obtener una vista previa ordenada, corregir lo que haga falta y descargar un `.xlsx` listo para usar.

## Gratis de verdad

Es totalmente gratis. Sin planes, sin bloqueos raros, sin "te dejo probar y despues te corto".

La meta es que cualquier contador o estudio lo pueda usar sin friccion y sin depender de herramientas caras.

## Para quien es

Para contadores, estudios contables y equipos administrativos que viven entre PDFs y planillas.

Si alguna vez hiciste copy/paste fila por fila desde un resumen bancario, este proyecto es para vos.

## Que hace

- `POST /api/v1/extract-preview`: recibe un PDF y devuelve una vista previa estructurada.
- `POST /api/v1/export-excel`: recibe la version final y devuelve el Excel.
- `GET /api/v1/health`: estado del servicio.

## Como mejora con el uso

La parte interesante pasa cuando corregis la preview editable:

1. Subis tu PDF y el sistema arma una primera version.
2. Vos corregis lo que haga falta (descripcion, montos, filas, etc.).
3. Al confirmar la exportacion, se genera una señal tecnica de esas correcciones.
4. Esa señal me llega a mi para mejorar el algoritmo de parseo y reducir errores en futuros casos.

Importante: esa señal no incluye el PDF ni movimientos bancarios completos. Llega en formato minimizado/anonimizado para mejorar el parser sin exponer informacion sensible.

## Privacidad

- No guardamos el PDF original una vez procesado.
- No persistimos movimientos bancarios completos en base de datos.
- No hay credenciales hardcodeadas en el repo.
- El nombre de descarga se limpia y siempre termina en `.xlsx`.
- Las correcciones que se usan para mejora llegan sin datos personales ni contenido completo del extracto.

En resumen: el foco es procesar, devolver el resultado y minimizar al maximo cualquier exposicion de datos sensibles.

## Nombre del archivo al descargar

En `POST /api/v1/export-excel` podes mandar `downloadFilename` (o `download_filename`):

- extension fija: `.xlsx`
- limite: 80 caracteres en el nombre base
- si no lo mandas, se usa `filename` + timestamp

## Correrlo local

```powershell
python -m venv .venv
python -m pip --python .\.venv\Scripts\python.exe install -r .\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

## Docker

```powershell
docker build -t pasameloaexcel-backend .
docker run --rm -p 8000:8000 --env-file .\.env.local pasameloaexcel-backend
```
