import "./globals.css";
import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "IB Option Allocation & Change Feasibility Tool",
  description: "Local timetabling tool for IBDP option allocation and change requests",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-800">
        <AuthProvider>
          <div className="flex">
            <Nav />
            <main className="flex-1 p-6 min-w-0">{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
