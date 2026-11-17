# NOXTIUM: precios del CRM, cupo n8n y Software de restaurante

## Costos de infraestructura usados para estimar rentabilidad

El servidor/Proxmox fue pagado por $1.872.000 COP por un año, equivalente a reservar $156.000 COP/mes para la renovación. La IA de imágenes 3D cuesta $62.000 COP/mes. Costos identificados: $218.000 COP/mes o $2.616.000 COP/año, antes del dominio, impuestos, copias de seguridad, pasarela de pago, soporte y modelos de IA conversacional. Estos costos son una estimación del operador, no se cobran automáticamente a los clientes.

## Precios del CRM + Agentes comerciales

El catálogo se sincroniza al abrir el panel de servicios y corrige también los precios de planes que ya existen en PostgreSQL:

| Plan | Precio | Duración | Cupo inicial de tokens de IA para el período |
|---|---:|---|---:|
| Profesional mensual | $300.000 COP | 1 mes | 100.000 |
| Trimestral | $800.000 COP | 3 meses | 300.000 |
| Anual | $1.200.000 COP | 12 meses | 1.200.000 |

Los cupos son valores iniciales configurables. Ajustarlos en `.env` sin compartir el archivo:

```dotenv
NOXTIUM_CRM_MONTHLY_TOKENS=100000
NOXTIUM_CRM_QUARTERLY_TOKENS=300000
NOXTIUM_CRM_ANNUAL_TOKENS=1200000
```

El cupo se asigna a la suscripción cuando el administrador aprueba el pago y se reinicia al activar un plan nuevo/renovado. La vista del cliente muestra el límite, el consumo informado y el saldo restante.

**Importante sobre el término “tokens”:** son tokens de entrada/salida que consume el modelo de IA de la automatización. n8n es el orquestador; no genera por sí solo esos tokens. Para que el consumo sea medible, el flujo debe consultar saldo antes de llamar al modelo y reportar el uso real que entregue el proveedor del modelo.

## Endpoints protegidos para n8n

Ambos endpoints exigen `Authorization: Bearer <N8N_WEBHOOK_SECRET>` y deben llamarse desde el servidor/flujo de n8n, nunca desde el navegador del cliente.

### 1. Consultar saldo antes del nodo de IA

```http
GET https://TU-DOMINIO-NOXTIUM/api/meta/n8n/token-balance?company_id=123
Authorization: Bearer TU_N8N_WEBHOOK_SECRET
```

La respuesta incluye `allowed`, `token_limit`, `tokens_used` y `tokens_remaining`. Si `allowed` es `false`, el flujo debe detenerse antes de ejecutar el modelo y no responder automáticamente al contacto.

### 2. Reportar el consumo real después del nodo de IA

```http
POST https://TU-DOMINIO-NOXTIUM/api/meta/n8n/token-usage
Authorization: Bearer TU_N8N_WEBHOOK_SECRET
Content-Type: application/json

{
  "company_id": 123,
  "event_id": "id-unico-de-ejecucion-y-nodo-modelo",
  "input_tokens": 850,
  "output_tokens": 320,
  "workflow_id": "workflow-restaurante"
}
```

`event_id` debe ser único por empresa y por llamada al modelo. Si el flujo reintenta el reporte con el mismo identificador, NOXTIUM no suma el consumo dos veces. Mapea `input_tokens` y `output_tokens` a los campos de uso que realmente devuelva el proveedor/modelo; no uses estimaciones si el proveedor da métricas exactas.

Orden sugerido del flujo:

1. Recibir el evento de WhatsApp desde NOXTIUM.
2. Consultar el saldo con `token-balance`.
3. Si `allowed` es falso, finalizar sin llamar al modelo.
4. Ejecutar el nodo del modelo de IA.
5. Registrar los tokens reales con `token-usage`.
6. Solo si hay saldo y el registro se completó, enviar la respuesta por `/api/meta/send-message`.

NOXTIUM detiene la entrega de nuevos eventos a n8n cuando el cupo queda agotado y su endpoint de envío rechaza respuestas sin saldo. El reporte de tokens debe incorporarse al flujo de producción; el flujo de prueba con respuesta fija no demuestra todavía medición real de tokens de un modelo.

## Inventario para colegios

Precios comerciales propuestos para publicar en NOXTIUM:

| Plan | Precio | Duración |
|---|---:|---|
| Mensual | $180.000 COP | 1 mes |
| Trimestral | $480.000 COP | 3 meses |
| Anual | $1.800.000 COP | 12 meses |

Se pueden cambiar desde las variables `NOXTIUM_INVENTORY_MONTHLY_PRICE`, `NOXTIUM_INVENTORY_QUARTERLY_PRICE` y `NOXTIUM_INVENTORY_ANNUAL_PRICE`. El producto se describe como inventario para colegios; confirma que las funciones del proyecto cubren los procesos específicos de una institución educativa antes de publicitarlo como solución escolar completa.

## Software de restaurante

El producto visible se denomina **Software de restaurante**. El identificador interno `imperio-del-barril` se conserva para no romper URLs ni registros históricos, pero no debe mostrarse como nombre comercial.

Los precios se cargan como valores de activación/implementación, ya que no se había definido una periodicidad de renovación:

| Módulo | Valor |
|---|---:|
| Menú digital | $100.000 COP |
| Meseros y comandas | $250.000 COP |
| Cocina | $250.000 COP |
| Caja y ventas | $350.000 COP |
| Asistencia del personal | $150.000 COP |
| Inventario y alertas | $250.000 COP |
| Reportes e indicadores | $150.000 COP |
| **Paquete completo** | **$1.500.000 COP** |

Los siete módulos individuales suman $1.500.000 COP. Además, el plan de operación/actualizaciones/soporte básico se propone en $150.000 al mes, $420.000 por 3 meses o $1.500.000 por 12 meses; el costo de activar los módulos es adicional. Un cliente puede comprar módulos distintos con el mismo usuario/empresa aunque ya tenga el CRM; comprar uno no cancela los demás. El paquete completo sustituye los módulos individuales activos cuando el pago del paquete se aprueba. El alcance exacto del soporte debe definirse comercialmente para no prometer atención ilimitada.

Después de aprobar el pago del software de restaurante, su cuenta sigue un proceso de alta independiente. El administrador registra la empresa en esa aplicación y entrega el enlace desde el panel de NOXTIUM. No se mezcla su base de datos con la del CRM.

## Migración y despliegue

La nueva revisión se llama `20261020_tokens_modules` y depende de `20261020_remove_qr`. Antes de migrar, revisa `alembic current`. Si la base está en la cadena esperada, ejecuta:

```powershell
alembic upgrade head
```

Haz primero copia de seguridad del proyecto y PostgreSQL. No reemplaces el `.env`, la `FERNET_KEY`, las credenciales de Meta ni `N8N_WEBHOOK_SECRET` por valores del ZIP.
