"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { auth, User } from "@/lib/api";

const Ctx = createContext<{ user: User | null; isAdmin: boolean; logout: () => void }>({
  user: null, isAdmin: false, logout: () => {},
});

export const useAuth = () => useContext(Ctx);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    const u = auth.user();
    setUser(u);
    setReady(true);
    if (!u && path !== "/login") router.replace("/login");
  }, [path, router]);

  const logout = () => {
    auth.clear();
    setUser(null);
    router.replace("/login");
  };

  if (!ready) return null;
  if (!user && path !== "/login") return null;
  return <Ctx.Provider value={{ user, isAdmin: user?.role === "ADMIN", logout }}>{children}</Ctx.Provider>;
}
