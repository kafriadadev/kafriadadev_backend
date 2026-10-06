/*
 * One icon family: Tabler (MIT), rendered as inline SVG on the server, so icons
 * work with JavaScript off. Pages import icons from here, never from Tabler
 * directly, so the set stays small and consistent.
 *
 * The football icons Tabler lacks (whistle, yellow and red card, VAR screen,
 * position badge) are drawn below on the same 24px grid and 2px stroke.
 * Sizes: 16, 20, 24, 32. An icon is never the only carrier of meaning: it sits
 * beside a word.
 */
import type { SVGProps } from "react";

export {
  IconBallFootball,
  IconShirtSport,
  IconSoccerField,
  IconPlayFootball,
  IconScoreboard,
  IconIdBadge2,
  IconQrcode,
  IconScan,
  IconTrophy,
  IconCash,
  IconShieldCheck,
  IconMapPin,
  IconFlag,
  IconCheck,
  IconAlertTriangle,
  IconInfoCircle,
  IconUser,
  IconUsersGroup,
  IconSearch,
  IconPhone,
  IconMail,
  IconLock,
  IconDownload,
  IconPrinter,
  IconShare,
  IconBrandWhatsapp,
  IconCopy,
  IconArrowRight,
  IconArrowLeft,
  IconChevronRight,
  IconMenu2,
  IconX,
  IconCamera,
  IconCalendar,
  IconHome,
  IconLogout,
  IconWifiOff,
  IconClock,
  IconCreditCard,
  IconRefresh,
} from "@tabler/icons-react";

type IconProps = Omit<SVGProps<SVGSVGElement>, "stroke"> & {
  size?: 16 | 20 | 24 | 32 | number;
  stroke?: number;
  title?: string;
};

function Base({ size = 24, stroke = 2, title, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

/** Information, nothing wrong. */
export function IconWhistle(p: IconProps) {
  return (
    <Base {...p}>
      <circle cx="9" cy="15" r="5" />
      <path d="M13 12l8-3.5v3.5l-6.2 2.6" />
      <circle cx="9" cy="15" r="1" />
      <path d="M5 4.5l1.5 2M9.5 3v2.5M14 4.5l-1.5 2" />
    </Base>
  );
}

/** Something to fix; you can carry on. The fill is the warning colour. */
export function IconYellowCard(p: IconProps) {
  return (
    <Base {...p}>
      <rect x="7" y="3" width="11" height="16" rx="2" transform="rotate(12 12.5 11)" fill="var(--yellow-card)" />
    </Base>
  );
}

/** Blocked or failed. */
export function IconRedCard(p: IconProps) {
  return (
    <Base {...p}>
      <rect x="7" y="3" width="11" height="16" rx="2" transform="rotate(12 12.5 11)" fill="var(--card-red)" />
    </Base>
  );
}

/** Being checked: the referee's drawn rectangle. */
export function IconVarScreen(p: IconProps) {
  return (
    <Base {...p}>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <rect x="7" y="7.5" width="10" height="6" rx="1" strokeDasharray="2 2" />
      <path d="M9 21h6M12 17v4" />
    </Base>
  );
}

export type Position = "GK" | "DF" | "MF" | "FW";

/** A shirt with the position on the chest. Use at 32px or larger. */
export function IconPosition({ position, ...p }: IconProps & { position: Position }) {
  return (
    <Base {...p}>
      <path d="M8 3l-5 3 2 4 2.5-1V21h9V9l2.5 1 2-4-5-3c-.5 1.5-2 2.5-4 2.5S8.5 4.5 8 3z" />
      <text
        x="12"
        y="16.5"
        textAnchor="middle"
        fontSize="6.5"
        fontWeight="800"
        fontFamily="var(--font-display)"
        fill="currentColor"
        stroke="none"
      >
        {position}
      </text>
    </Base>
  );
}
