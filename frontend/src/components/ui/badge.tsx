import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Badges are stamps: uppercase, tracked, in the machine voice, on a hairline rather
 * than a fill — C separates with outline and colour, never with a filled chip.
 *
 * The band variants encode the three verdicts. `confident` is settled and takes
 * primary ink at the heaviest weight; `uncertain` is measured but unresolved and
 * takes the measure colour; `no match` is a refusal to name and takes refuse.
 */
const badgeVariants = cva(
  "stamp inline-flex items-center rounded-sm border px-2 py-0.5 font-medium",
  {
    variants: {
      variant: {
        default: "border-border text-muted-foreground",
        confident: "border-foreground/25 font-semibold text-foreground",
        uncertain: "border-measure/40 text-measure",
        no_match: "border-refuse/40 text-refuse",
        instruct: "border-instruct/40 text-instruct",
        refuse: "border-refuse/40 text-refuse",
        measure: "border-measure/40 text-measure",
        secondary: "border-border text-muted-foreground",
        destructive: "border-refuse/40 text-refuse",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
