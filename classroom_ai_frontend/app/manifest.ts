import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
 return { id: "/", name: "غياب المعالي", short_name: "غياب المعالي", description: "إدارة حضور وغياب طلاب مدارس المعالي", lang: "ar", dir: "rtl", start_url: "/", scope: "/", display: "standalone", background_color: "#F7F5F0", theme_color: "#0F4C3A", icons: [
 {src:"/icons/maali-192.png", sizes:"192x192", type:"image/png", purpose:"any"},
 {src:"/icons/maali-512.png", sizes:"512x512", type:"image/png", purpose:"any"},
 {src:"/icons/maali-maskable.png", sizes:"512x512", type:"image/png", purpose:"maskable"}
 ] };
}
