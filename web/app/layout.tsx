import "./globals.css";

export const metadata = {
  title: "Streaming Chat",
  description: "Simple streaming chat UI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
