import { useActionData, useNavigation, Form, useLoaderData } from "react-router";
import { useRef, useState } from "react";
import { authenticate } from "../shopify.server";
import { getLeads, sendMessage, sendImage } from "../lib/bot-api.server";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  try {
    const leads = await getLeads("todos", 500);
    return { leads };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    return { leads: [] };
  }
};

export const action = async ({ request }) => {
  if (request.method !== "POST") {
    return null;
  }

  const { admin } = await authenticate.admin(request);
  const formData = await request.formData();
  const telefono = formData.get("telefono");
  const messageType = formData.get("messageType");
  const mensaje = formData.get("mensaje");
  const imagen = formData.get("imagen");
  const caption = formData.get("caption");

  if (!telefono) {
    return { error: "Selecciona un contacto" };
  }

  try {
    if (messageType === "texto" && mensaje) {
      const result = await sendMessage(telefono, mensaje);
      return {
        success: result.exito,
        mensaje: result.mensaje || "Mensaje enviado",
      };
    } else if ((messageType === "imagen" || messageType === "mixto") && imagen) {
      const result = await sendImage(telefono, imagen, caption || "");
      return {
        success: result.exito,
        mensaje: result.mensaje || "Imagen enviada",
      };
    } else {
      return { error: "Completa todos los campos requeridos" };
    }
  } catch (error) {
    return { error: error.message, success: false };
  }
};

export default function DashboardMessages() {
  const { leads } = useLoaderData();
  const actionData = useActionData();
  const navigation = useNavigation();
  const [selectedLead, setSelectedLead] = useState("");
  const [messageType, setMessageType] = useState("texto");
  const [searchQuery, setSearchQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const fileInputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const isLoading = navigation.state === "submitting";

  // Filter leads based on search
  const filteredLeads = leads.filter((lead) =>
    lead.nombre.toLowerCase().includes(searchQuery.toLowerCase()) ||
    lead.telefono.includes(searchQuery)
  );

  const handleLeadSelect = (lead) => {
    setSelectedLead(lead.telefono);
    setSearchQuery(lead.nombre);
    setShowDropdown(false);
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#18181B]">Enviar Mensajes</h1>
        <p className="text-sm text-[#71717A] mt-1">
          Comunícate con leads individuales
        </p>
      </div>

      <Form method="post" encType="multipart/form-data" className="space-y-6">
        {/* Contact Selection */}
        <div>
          <label className="block text-sm font-semibold text-[#18181B] mb-2">
            Contacto
          </label>
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setShowDropdown(true);
                setSelectedLead("");
              }}
              onFocus={() => setShowDropdown(true)}
              placeholder="Busca por nombre o teléfono..."
              className="w-full px-4 py-2 border border-[#E8E8E5] rounded-lg text-[#18181B] focus:outline-none focus:border-[#18181B]"
            />
            <input
              type="hidden"
              name="telefono"
              value={selectedLead}
            />

            {/* Dropdown */}
            {showDropdown && filteredLeads.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-[#E8E8E5] rounded-lg shadow-lg z-10 max-h-60 overflow-y-auto">
                {filteredLeads.slice(0, 20).map((lead) => (
                  <button
                    key={lead.telefono}
                    type="button"
                    onClick={() => handleLeadSelect(lead)}
                    className="w-full px-4 py-3 text-left border-b border-[#E8E8E5] hover:bg-[#FAFAF9] transition-colors last:border-b-0"
                  >
                    <p className="font-medium text-[#18181B]">{lead.nombre}</p>
                    <p className="text-xs text-[#71717A] font-mono">
                      {lead.telefono}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
          {selectedLead && (
            <p className="text-xs text-[#16A34A] mt-2 font-mono">
              ✓ {selectedLead}
            </p>
          )}
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

        {/* Compose Area */}
        {(messageType === "texto" || messageType === "mixto") && (
          <div>
            <label className="block text-sm font-semibold text-[#18181B] mb-2">
              {messageType === "mixto" ? "Mensaje (opcional)" : "Mensaje"}
            </label>
            <textarea
              name="mensaje"
              placeholder="Escribe tu mensaje..."
              rows="6"
              className="w-full px-4 py-3 border border-[#E8E8E5] rounded-lg text-[#18181B] placeholder-[#A1A1A1] focus:outline-none focus:border-[#18181B] resize-none"
              required={messageType === "texto"}
            />
          </div>
        )}

        {/* Image Upload */}
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
                    className="text-xs text-[#18181B] underline hover:no-underline"
                  >
                    Seleccionar archivo
                  </button>
                </div>
              </div>
            </div>

            {(messageType === "mixto") && (
              <div>
                <label className="block text-sm font-semibold text-[#18181B] mb-2">
                  Texto de la imagen (opcional)
                </label>
                <textarea
                  name="caption"
                  placeholder="Descripción o comentario..."
                  rows="3"
                  className="w-full px-4 py-3 border border-[#E8E8E5] rounded-lg text-[#18181B] placeholder-[#A1A1A1] focus:outline-none focus:border-[#18181B] resize-none"
                />
              </div>
            )}
          </div>
        )}

        {/* Send Button */}
        <button
          type="submit"
          disabled={!selectedLead || isLoading}
          className="w-full px-4 py-3 bg-[#16A34A] text-white rounded-lg font-medium hover:bg-[#15803D] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? "Enviando..." : "✉️ Enviar"}
        </button>
      </Form>

      {/* Result */}
      {actionData && !isLoading && (
        <div
          className={`mt-6 p-4 rounded-lg ${
            actionData.success
              ? "bg-[#F0FDF4] border border-[#D1FAE5]"
              : "bg-[#FEF2F2] border border-[#FEE2E2]"
          }`}
        >
          <p
            className={`text-sm font-medium ${
              actionData.success ? "text-[#065F46]" : "text-[#991B1B]"
            }`}
          >
            {actionData.success ? "✅" : "❌"} {actionData.mensaje || actionData.error}
          </p>
        </div>
      )}
    </div>
  );
}
