import { Form, useActionData, useNavigation } from "react-router";
import { useRef, useState } from "react";
import { authenticate } from "../shopify.server";
import { importExcel } from "../lib/bot-api.server";

export const action = async ({ request }) => {
  if (request.method !== "POST") {
    return null;
  }

  const { admin } = await authenticate.admin(request);
  const formData = await request.formData();
  const file = formData.get("archivo");

  if (!file) {
    return { error: "No file selected" };
  }

  try {
    const buffer = await file.arrayBuffer();
    const result = await importExcel(buffer, file.name);
    return {
      success: true,
      exitosos: result.exitosos || 0,
      duplicados: result.duplicados || 0,
      errores: result.errores || 0,
      total: result.total || 0,
      detalles: result.detalles || [],
    };
  } catch (error) {
    return {
      success: false,
      error: error.message,
      detalles: [],
    };
  }
};

export default function DashboardLeadsImport() {
  const actionData = useActionData();
  const navigation = useNavigation();
  const fileInputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);

  const isLoading = navigation.state === "submitting";

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      fileInputRef.current.files = e.dataTransfer.files;
    }
  };

  const handleChange = (e) => {
    if (e.target.files) {
      fileInputRef.current.files = e.target.files;
    }
  };

  return (
    <div className="p-6 max-w-2xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#18181B]">Importar Leads</h1>
        <p className="text-sm text-[#71717A] mt-1">
          Sube un archivo Excel (.xlsx, .xls) o CSV con tus contactos
        </p>
      </div>

      {/* Upload Zone */}
      <Form method="post" encType="multipart/form-data">
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors mb-6 ${
            dragActive
              ? "border-[#16A34A] bg-[#F0FDF4]"
              : "border-[#D8D8D5] bg-[#FAFAF9]"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            name="archivo"
            accept=".xlsx,.xls,.csv"
            onChange={handleChange}
            className="hidden"
            disabled={isLoading}
          />

          <div className="flex flex-col items-center gap-3">
            <span className="text-4xl">📁</span>
            <div>
              <p className="font-medium text-[#18181B]">
                Arrastra tu archivo aquí
              </p>
              <p className="text-sm text-[#71717A] mt-1">
                o haz clic para seleccionar
              </p>
            </div>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              className="mt-3 px-4 py-2 bg-[#18181B] text-white rounded-lg text-sm font-medium hover:bg-[#2A2A29] disabled:opacity-50"
            >
              Seleccionar archivo
            </button>
            <p className="text-xs text-[#71717A] mt-2">
              Excel (.xlsx, .xls) o CSV — máx 10 MB
            </p>
          </div>
        </div>

        {/* File Name Display */}
        {fileInputRef.current?.files?.[0] && (
          <div className="mb-6 p-3 bg-[#F0FDF4] border border-[#D1FAE5] rounded-lg">
            <p className="text-sm text-[#065F46]">
              📄 {fileInputRef.current.files[0].name}
            </p>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={!fileInputRef.current?.files?.[0] || isLoading}
          className="w-full px-4 py-3 bg-[#16A34A] text-white rounded-lg font-medium hover:bg-[#15803D] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? "Importando..." : "Importar Leads"}
        </button>
      </Form>

      {/* Results */}
      {actionData && !isLoading && (
        <div className="mt-8 space-y-4">
          {actionData.success ? (
            <div className="p-6 bg-[#F0FDF4] border border-[#D1FAE5] rounded-lg">
              <div className="flex items-start gap-3 mb-4">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="font-semibold text-[#065F46]">
                    Importación exitosa
                  </h3>
                  <p className="text-sm text-[#047857] mt-1">
                    Se procesaron {actionData.total} contactos
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 bg-white border border-[#D1FAE5] rounded">
                  <p className="text-xs text-[#71717A] uppercase font-semibold">
                    Añadidos
                  </p>
                  <p className="text-2xl font-bold text-[#16A34A] mt-1">
                    {actionData.exitosos}
                  </p>
                </div>
                <div className="p-3 bg-white border border-[#FEF3C7] rounded">
                  <p className="text-xs text-[#71717A] uppercase font-semibold">
                    Duplicados
                  </p>
                  <p className="text-2xl font-bold text-[#D97706] mt-1">
                    {actionData.duplicados}
                  </p>
                </div>
                <div className="p-3 bg-white border border-[#FEE2E2] rounded">
                  <p className="text-xs text-[#71717A] uppercase font-semibold">
                    Errores
                  </p>
                  <p className="text-2xl font-bold text-[#DC2626] mt-1">
                    {actionData.errores}
                  </p>
                </div>
              </div>

              {actionData.detalles && actionData.detalles.length > 0 && (
                <div className="mt-4 pt-4 border-t border-[#D1FAE5]">
                  <p className="text-xs font-semibold text-[#065F46] uppercase mb-3">
                    Primeros errores ({actionData.detalles.length})
                  </p>
                  <div className="space-y-2">
                    {actionData.detalles.slice(0, 10).map((detail, idx) => (
                      <div
                        key={idx}
                        className="text-sm text-[#047857] bg-white p-2 rounded"
                      >
                        <p className="font-mono text-xs">
                          Fila {detail.row || idx + 1}
                        </p>
                        <p>{detail.razon || detail.error || "Error desconocido"}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-6 bg-[#FEF2F2] border border-[#FEE2E2] rounded-lg">
              <div className="flex items-start gap-3">
                <span className="text-2xl">❌</span>
                <div>
                  <h3 className="font-semibold text-[#991B1B]">
                    Error en la importación
                  </h3>
                  <p className="text-sm text-[#B91C1C] mt-1">
                    {actionData.error}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Helper Text */}
      <div className="mt-8 p-4 bg-[#F9FAFB] border border-[#E8E8E5] rounded-lg text-sm text-[#71717A]">
        <p className="font-medium text-[#18181B] mb-2">💡 Formato esperado:</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>Columna A: Nombre</li>
          <li>Columna B: Teléfono (con o sin +595)</li>
          <li>Columna C: Producto preferido (opcional)</li>
          <li>Primera fila: encabezados (se ignora)</li>
        </ul>
      </div>
    </div>
  );
}
