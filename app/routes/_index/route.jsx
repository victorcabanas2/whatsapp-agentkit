import { redirect } from "react-router";

export const loader = async ({ request }) => {
  const url = new URL(request.url);

  if (url.searchParams.get("shop")) {
    throw redirect(`/app?${url.searchParams.toString()}`);
  }

  // In development, use /dev dashboard. In production, use /app
  const isDev = process.env.ENVIRONMENT !== "production";
  throw redirect(isDev ? "/dev" : "/app");
};
