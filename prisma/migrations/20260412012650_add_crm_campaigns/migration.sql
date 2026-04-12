-- CreateTable
CREATE TABLE "Campaign" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "nombre" TEXT NOT NULL,
    "mensaje" TEXT NOT NULL,
    "audiencia" TEXT NOT NULL DEFAULT 'todos',
    "estado" TEXT NOT NULL DEFAULT 'draft',
    "exitosos" INTEGER NOT NULL DEFAULT 0,
    "fallidos" INTEGER NOT NULL DEFAULT 0,
    "total" INTEGER NOT NULL DEFAULT 0,
    "creadoEn" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "enviadoEn" DATETIME
);

-- CreateTable
CREATE TABLE "CampaignRecipient" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "campaignId" INTEGER NOT NULL,
    "telefono" TEXT NOT NULL,
    "nombre" TEXT NOT NULL DEFAULT '',
    "estado" TEXT NOT NULL DEFAULT 'pending',
    "enviadoEn" DATETIME,
    CONSTRAINT "CampaignRecipient_campaignId_fkey" FOREIGN KEY ("campaignId") REFERENCES "Campaign" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
