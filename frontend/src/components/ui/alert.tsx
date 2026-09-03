import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * One variant per message class — see design/ROUND-2-CONTEXT.md. These existed
 * nowhere before the lock, so three call sites hand-rolled `border-warning/30
 * bg-warning/5` and then added `text-foreground` to the description to undo the
 * colour they had just inherited.
 *
 * C carries an alert on a left mark and a colour, not on a filled panel: the ground
 * stays flat.
 */
const alertVariants = cva(
  "relative w-full rounded-sm border-l-2 py-2.5 pl-3.5 pr-4 text-sm [&>svg]:absolute [&>svg]:left-3.5 [&>svg]:top-3 [&>svg~*]:pl-6",
  {
    variants: {
      variant: {
        default: "border-l-border text-foreground",
        /** something was rejected or failed */
        refuse: "border-l-refuse text-refuse [&_[data-slot=body]]:text-foreground",
        destructive: "border-l-refuse text-refuse [&_[data-slot=body]]:text-foreground",
        /** what to do next */
        instruct: "border-l-instruct text-instruct [&_[data-slot=body]]:text-foreground",
        /** a measured value worth noticing */
        measure: "border-l-measure text-measure [&_[data-slot=body]]:text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
))
Alert.displayName = "Alert"

const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h5 ref={ref} className={cn("stamp mb-1 font-medium", className)} {...props} />
))
AlertTitle.displayName = "AlertTitle"

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("text-sm [&_p]:leading-relaxed", className)} {...props} />
))
AlertDescription.displayName = "AlertDescription"

export { Alert, AlertTitle, AlertDescription }
