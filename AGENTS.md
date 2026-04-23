# PasameloaExcel

## Reglas generales
- Antes de modificar el backend, revisar si existe una skill adecuada en `.agents/skills`.
- Preferir cambios mínimos, claros y compatibles hacia atrás.
- No mover lógica de negocio a routers ni mezclar responsabilidades entre capas.
- Proteger privacidad: no persistir PDFs, credenciales, datos bancarios sensibles ni información personal innecesaria.
- Mantener el proyecto apto para open source: evitar ejemplos reales, secretos hardcodeados, logs sensibles y fixtures con datos verdaderos.
- Ejecutar tests focalizados según el área tocada.
- Si el cambio afecta parsing, exportación o contratos API, explicar brevemente riesgos de regresión.