"use client";

import { FingerprintIcon, Menu, Moon, Sun } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { motion } from "motion/react";

export function AcmeHero() {
  return (
    <div className="container max-w-5xl mx-auto">
      <header className="relative pt-4">
        <nav className="flex items-center justify-between rounded-xl bg-background py-2 px-4 shadow-lg border">
          <div className="flex items-center space-x-6">
            <a href="#" className="text-base font-semibold">Acme</a>
            <div className="hidden md:flex items-center space-x-6">
              {["Docs", "Components", "Templates", "Pricing"].map((label) => (
                <a key={label} href="#" className="text-sm text-muted-foreground/60 hover:text-foreground/80 transition-colors">
                  {label}
                </a>
              ))}
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <Button variant="ghost" size="icon" className="h-7 w-7">
              <Sun className="h-[15px] w-[15px] rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-[15px] w-[15px] rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
              <span className="sr-only">Toggle theme</span>
            </Button>
            <Separator orientation="vertical" className="h-6" />
            <Button variant="ghost" className="hidden md:inline-flex h-7 px-2 text-sm font-normal text-muted-foreground/60 hover:text-foreground/80">
              Sign in
            </Button>
            <Button className="hidden md:inline-flex h-7 rounded-full bg-foreground px-3 text-sm font-normal text-background hover:bg-foreground/90">
              Get access
            </Button>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 md:hidden">
                  <Menu className="h-[15px] w-[15px]" />
                  <span className="sr-only">Open menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[240px] sm:w-[300px]">
                <nav className="flex flex-col space-y-4">
                  {["Docs", "Components", "Templates", "Pricing"].map((label) => (
                    <a key={label} href="#" className="text-sm text-muted-foreground/60 hover:text-foreground/80 transition-colors">
                      {label}
                    </a>
                  ))}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </nav>
      </header>

      <main className="relative container px-2 mx-auto">
        <section className="w-full py-12 md:py-24">
          <motion.div
            className="flex flex-col items-center space-y-6 text-center"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <motion.h1
              className="text-4xl font-bold tracking-tighter sm:text-5xl md:text-6xl"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.5 }}
            >
              Websites, Redefined
            </motion.h1>
            <motion.p
              className="mx-auto max-w-xl text-md sm:text-2xl text-muted-foreground"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
            >
              Ship your projects with{" "}
              <span className="font-semibold text-foreground">beautiful components</span>
            </motion.p>
            <motion.div
              className="flex flex-col sm:flex-row gap-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.5 }}
            >
              <Button className="rounded-xl bg-foreground text-background hover:bg-foreground/90">
                Explore Components
                <FingerprintIcon className="ml-2 w-5 h-5 hidden sm:inline" />
              </Button>
            </motion.div>
            <motion.div
              className="w-full border p-2 rounded-3xl"
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6, duration: 0.8 }}
            >
              <div className="relative w-full rounded-3xl overflow-hidden border shadow-2xl">
                <img
                  src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&q=80"
                  alt="Dashboard Preview"
                  className="w-full h-full object-cover rounded-3xl"
                />
              </div>
            </motion.div>
          </motion.div>
        </section>
      </main>
    </div>
  );
}
