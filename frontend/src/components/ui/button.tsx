import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Variants are message classes, not decoration — see design/ROUND-2-CONTEXT.md.
 *
 * `instruct` is the primary action: it is the system telling you what to do next, and
 * it carries the display face because that is a human statement rather than machine
 * speech. `refuse` is for irreversible and destructive actions only.
 *
 * Before the lock there was no accent variant at all, so five call sites pasted the
 * identical override string and the one button that did not — "Finalize session",
 * the most consequential action in the app — ended up as the only differently
 * coloured button in the product, by accident.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:border-border disabled:bg-muted disabled:text-muted-foreground [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        instruct:
          "bg-instruct font-display font-medium tracking-tight text-instruct-foreground hover:bg-instruct/90",
        default:
          "bg-primary font-display font-medium tracking-tight text-primary-foreground hover:bg-primary/90",
        refuse:
          "bg-refuse font-display font-medium tracking-tight text-refuse-foreground hover:bg-refuse/90",
        // Kept as an alias so shadcn call sites that ask for `destructive` land on
        // the refuse class rather than silently falling through to `default`.
        destructive:
          "bg-refuse font-display font-medium tracking-tight text-refuse-foreground hover:bg-refuse/90",
        // These previously said `hover:bg-accent`, which — once accent became a real
        // brand colour — made every secondary button flip to a solid fill on hover.
        outline:
          "border border-input bg-background hover:bg-muted hover:text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-muted",
        ghost: "hover:bg-muted hover:text-foreground",
        link: "text-instruct underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-6 text-lg",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
