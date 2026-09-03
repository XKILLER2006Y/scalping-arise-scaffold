export const metadata = { title: "Scalping Arise", description: "XAU/USD analysis scaffold" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body style={{ margin: 0, background: "#0b0e14", color: "#e6e6e6" }}>{children}</body></html>);
}
