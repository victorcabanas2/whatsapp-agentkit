import { useActionData, useNavigation, Form, useNavigate, useLoaderData } from "react-router";
import { useRef, useState } from "react";
import { authenticate } from "../shopify.server";
import db from "../db.server";
import { getLeads, sendMessage, sendImage } from "../lib/bot-api.server";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);

  try {
    const leads = await getLeads("todos", 500);
    const hot = leads.filter((l) => l.intencion === "hot").length;
    const warm = leads.filter((l) => l.intencion === "warm").length;
    const cold = leads.filter((l) => l.intencion === "cold").length;

    return {
      stats: {
        total: leads.length,
        hot,
        warm,
        cold,
      },
    };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    return {
      stats: {
        total: 654,
        hot: 42,
        warm: 178,
        cold: 434,
      },
    };
  }
};

export const action = async ({ request }) => {
  if (request.method !== "POST") {
    return null;
  }

  const { admin } = await authenticate.admin(request);
  const formData = await request.formData();
  const nombre = formData.get("nombre");
  const audiencia = formData.get("audiencia");
  const messageType = formData.get("messageType");
  const mensaje = formData.get("mensaje");
  const imagen = formData.get("imagen");
  const caption = formData.get("caption");
  const action_type = formData.get("action_type"); // "guardar" o "enviar"

  if (!nombre || !audiencia) {
    return { error: "Completa nombre y audiencia" };
  }

  try {
    // Get leads based on audiencia
    let leads = [];
    try {
      const allLeads = await getLeads("todos", 500);
      if (audiencia === "hot") {
        leads = allLeads.filter((l) => l.intencion === "hot");
      } else if (audiencia === "warm") {
        leads = allLeads.filter((l) => l.intencion === "warm");
      } else if (audiencia === "cold") {
        leads = allLeads.filter((l) => l.intencion === "cold");
      } else {
        leads = allLeads;
      }
    } catch (e) {
      console.log("getLeads failed:", e.message);
      leads = [];
    }

    // Create campaign record
    const campaign = await db.campaign.create({
      data: {
        nombre,
        audiencia,
        estado: action_type === "enviar" ? "enviando" : "borrador",
      },
    });

    // Create recipients
    let exitosos = 0;
    let fallidos = 0;

    if (action_type === "enviar" && leads.length > 0) {
      // Send messages with delay
      for (const lead of leads) {
        try {
          let result;
          if (messageType === "texto" && mensaje) {
            result = await sendMessage(lead.telefono, mensaje);
          } else if (
            (messageType === "imagen" || messageType === "mixto") &&
            imagen
          ) {
            result = await sendImage(lead.telefono, imagen, caption || "");
          } else {
            result = { exito: false };
          }

          await db.campaignRecipient.create({
            data: {
              campaignId: campaign.id,
              telefono: lead.telefono,
              estado: result.exito ? "enviado" : "error",
            },
          });

          if (result.exito) {
            exitosos++;
          } else {
            fallidos++;
          }

          // Delay 300ms between messages
          await new Promise((r) => setTimeout(r, 300));
        } catch (e) {
          console.log(`Error sending to ${lead.telefono}:`, e.message);
          fallidos++;
          await db.campaignRecipient.create({
            data: {
              campaignId: campaign.id,
              telefono: lead.telefono,
              estado: "error",
            },
          });
        }
      }

      // Update campaign with final stats
      await db.campaign.update({
        where: { id: campaign.id },
        data: {
          estado: "completada",
        },
      });

      return {
        success: true,
        mensaje: `Campaña completada: ${exitosos} enviados, ${fallidos} errores`,
        total: exitosos + fallidos,
        exitosos,
        fallidos,
        campaignId: campaign.id,
      };
    } else if (action_type === "guardar") {
      // Just create recipients without sending
      for (const lead of leads) {
        await db.campaignRecipient.create({
          data: {
            campaignId: campaign.id,
            telefono: lead.telefono,
            estado: "pendiente",
          },
        });
      }

      return {
        success: true,
        mensaje: `Borrador guardado con ${leads.length} contactos`,
        total: leads.length,
        campaignId: campaign.id,
      };
    }
  } catch (error) {
    return { error: error.message, success: false };
  }
};

export default function DashboardCampaignsNew() {
  const { stats } = useLoaderData();
  const actionData = useActionData();
  const navigation = useNavigation();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [audiencia, setAudiencia] = useState("todos");
  const [messageType, setMessageType] = useState("texto");
  const [selectedFile, setSelectedFile] = useState(null);
  const isLoading = navigation.state === "submitting";

  const getAudienciaCount = () => {
    switch (audiencia) {
      case "hot":
        return stats.hot;
      case "warm":
        return stats.warm;
      case "cold":
        return stats.cold;
      default:
        return stats.total;
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  // Success state
  if (actionData?.success && !isLoading) {
    return (
      <div className="p-6 max-w-2xl">
        <div className="text-center space-y-4">
          <div className="text-6xl">✅</div>
          <h1 className="text-3xl font-bold text-[#18181B]">
            {actionData.mensaje}
          </h1>
          <div className="grid grid-cols-3 gap-4 mt-6">
            <div className="p-4 bg-[#F0FDF4] rounded-lg">
              <p className="text-xs text-[#71717A] uppercase mb-1">Total</p>
              <p className="text-2xl font-bold text-[#16A34A]">
                {actionData.total}
              </p>
            </div>
            {actionData.exitosos > 0 && (
              <div className="p-4 bg-[#F0FDF4] rounded-lg">
                <p className="text-xs text-[#71717A] uppercase mb-1">Exitosos</p>
                <p className="text-2xl font-bold text-[#16A34A]">
                  {actionData.exitosos}
                </p>
              </div>
            )}
            {actionData.fallidos > 0 && (
              <div className="p-4 bg-[#FEF2F2] rounded-lg">
                <p className="text-xs text-[#71717A] uppercase mb-1">Errores</p>
                <p className="text-2xl font-bold text-[#DC2626]">
                  {actionData.fallidos}
                </p>
              </div>
            )}
          </div>
          <div className="pt-6 border-t border-[#E8E8E5]">
            <button
              onClick={() => navigate("/dashboard/campaigns")}
              className="px-4 py-2 bg-[#18181B] text-white rounded-lg font-medium hover:bg-[#2A2A29]"
            >
              Ver campañas →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#18181B]">Nueva Campaña</h1>
        <p className="text-sm text-[#71717A] mt-1">
          Crea y envía mensajes a múltiples contactos
        </p>
      </div>

      <Form method="post" encType="multipart/form-data" className="space-y-6">
        {/* Campaign Name */}
        <div>
          <label className="block text-sm font-semibold text-[#18181B] mb-2">
            Nombre de campaña
          </label>
          <input
            type="text"
            name="nombre"
            placeholder="Ej: Bienvenida nuevos clientes"
            required
            className="w-full px-4 py-2 border border-[#E8E8E5] rounded-lg text-[#18181B] focus:outline-none focus:border-[#18181B]"
          />
        </div>

        {/* Audience Selection */}
        <div>
          <label className="block text-sm font-semibold text-[#18181B] mb-3">
            Audiencia
          </label>
          <div className="space-y-3">
            {[
              {
                value: "todos",
                label: `Todos (${stats.total})`,
                desc: "Todos los contactos",
              },
              {
                value: "hot",
                label: `Calientes (${stats.hot}) 🔥`,
                desc: "Score 70+",
              },
              {
                value: "warm",
                label: `Tibios (${stats.warm}) 🌡️`,
                desc: "Score 50-69",
              },
              {
                value: "cold",
                label: `Fríos (${stats.cold}) ❄️`,
                desc: "Score 0-49",
              },
            ].map((opt) => (
              <label
                key={opt.value}
                className="flex items-center p-3 border border-[#E8E8E5] rounded-lg cursor-pointer hover:bg-[#FAFAF9] transition-colors"
              >
                <input
                  type="radio"
                  name="audiencia"
                  value={opt.value}
                  checked={audiencia === opt.value}
                  onChange={(e) => setAudiencia(e.target.value)}
                  className="w-4 h-4 cursor-pointer"
                />
                <div className="ml-3">
                  <p className="font-medium text-[#18181B]">{opt.label}</p>
                  <p className="text-xs text-[#71717A]">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Message Type Tabs */}
        <div>
          <label className="block text-sm font-semibold text-[#18181B] mb-3">
            Tipo de mensaje
          </label>
          <div className="flex gap-3">
            {[
              { value: "texto", label: "📝 Solo texto" },
              { value: "imagen", label: "🖼️ Solo imagen" },
              { value: "mixto", label: "📸 Texto + imagen" },
            ].map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => {
                  setMessageType(tab.value);
                  setSelectedFile(null);
                }}
                className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                  messageType === tab.value
                    ? "bg-[#18181B] text-white"
                    : "bg-[#E8E8E5] text-[#18181B] hover:bg-[#D8D8D5]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Compose */}
        {(messageType === "texto" || messageType === "mixto") && (
          <div>
            <label className="block text-sm font-semibold text-[#18181B] mb-2">
              Mensaje
            </label>
            <textarea
              name="mensaje"
              placeholder="Escribe el mensaje para toda la audiencia..."
              rows="6"
              className="w-full px-4 py-3 border border-[#E8E8E5] rounded-lg text-[#18181B] focus:outline-none focus:border-[#18181B] resize-none"
              required={messageType === "texto"}
            />
          </div>
        )}

        {/* Image */}
        {(messageType === "imagen" || messageType === "mixto") && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-semibold text-[#18181B] mb-2">
                Imagen
              </label>
              <div className="border-2 border-dashed border-[#D8D8D5] rounded-lg p-6 text-center hover:border-[#18181B] transition-colors">
                <input
                  ref={fileInputRef}
                  type="file"
                  name="imagen"
                  accept="image/*"
                  onChange={handleFileChange}
                  className="hidden"
                  required={messageType === "imagen"}
                />
                <div className="flex flex-col items-center gap-2">
                  <span className="text-3xl">📸</span>
                  <p className="text-sm font-medium text-[#18181B]">
                    {selectedFile ? selectedFile.name : "Sube una imagen"}
                  </p>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="text-xs text-[#18181B] underline"
                  >
                    Seleccionar
                  </button>
                </div>
              </div>
            </div>

            {messageType === "mixto" && (
              <div>
                <label className="block text-sm font-semibold text-[#18181B] mb-2">
                  Texto de la imagen (opcional)
                </label>
                <textarea
                  name="caption"
                  placeholder="Descripción..."
                  rows="3"
                  className="w-full px-4 py-3 border border-[#E8E8E5] rounded-lg text-[#18181B] focus:outline-none focus:border-[#18181B] resize-none"
                />
              </div>
            )}
          </div>
        )}

        {/* Preview */}
        <div className="p-4 bg-[#F9FAFB] border border-[#E8E8E5] rounded-lg">
          <p className="text-sm font-semibold text-[#18181B] mb-2">
            📊 Resumen
          </p>
          <div className="text-sm text-[#71717A] space-y-1">
            <p>
              Se enviará a{" "}
              <span className="font-bold text-[#18181B]">
                {getAudienciaCount()}
              </span>{" "}
              contactos
            </p>
            <p>
              Tipo:{" "}
              <span className="font-bold text-[#18181B]">
                {messageType === "texto"
                  ? "Texto"
                  : messageType === "imagen"
                  ? "Imagen"
                  : "Texto + Imagen"}
              </span>
            </p>
          </div>
        </div>

        {/* Action Error */}
        {actionData?.error && !actionData.success && (
          <div className="p-4 bg-[#FEF2F2] border border-[#FEE2E2] rounded-lg">
            <p className="text-sm text-[#DC2626]">❌ {actionData.error}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            type="submit"
            name="action_type"
            value="enviar"
            disabled={isLoading}
            className="flex-1 px-4 py-3 bg-[#16A34A] text-white rounded-lg font-medium hover:bg-[#15803D] disabled:opacity-50 transition-colors"
          >
            {isLoading ? "Enviando..." : "✉️ Enviar ahora"}
          </button>
          <button
            type="submit"
            name="action_type"
            value="guardar"
            disabled={isLoading}
            className="flex-1 px-4 py-3 bg-[#E8E8E5] text-[#18181B] rounded-lg font-medium hover:bg-[#D8D8D5] disabled:opacity-50 transition-colors"
          >
            {isLoading ? "Guardando..." : "💾 Guardar borrador"}
          </button>
        </div>
      </Form>
    </div>
  );
}
