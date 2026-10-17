/* Íconos de trazo, 16×16, mismo grosor en todos. */
type P = { size?: number };

const svg = (size: number, children: React.ReactNode) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {children}
  </svg>
);

export const LockIcon = ({ size = 14 }: P) => svg(size, <><rect x="3" y="7" width="10" height="7" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></>);
export const EyeIcon = ({ size = 16 }: P) => svg(size, <><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z" /><circle cx="8" cy="8" r="2" /></>);
export const EyeOffIcon = ({ size = 16 }: P) => svg(size, <><path d="M6.6 3.7A6.5 6.5 0 0 1 8 3.5c4 0 6.5 4.5 6.5 4.5a11 11 0 0 1-1.7 2.2M4.2 4.9C2.5 6.1 1.5 8 1.5 8S4 12.5 8 12.5a6.4 6.4 0 0 0 3-.8" /><path d="M6.6 6.6a2 2 0 0 0 2.8 2.8M2 2l12 12" /></>);
export const ArrowIcon = ({ size = 16 }: P) => svg(size, <path d="M3 8h10M9 4l4 4-4 4" />);
export const LogoutIcon = ({ size = 16 }: P) => svg(size, <><path d="M6 14H3.5A1.5 1.5 0 0 1 2 12.5v-9A1.5 1.5 0 0 1 3.5 2H6" /><path d="M10.5 11 13.5 8l-3-3M13.5 8H6" /></>);
export const SendIcon = ({ size = 16 }: P) => svg(size, <><path d="M14 2 7 9" /><path d="M14 2 9.5 14 7 9 2 6.5 14 2Z" /></>);
export const ChevronIcon = ({ size = 16 }: P) => svg(size, <path d="m6 4 4 4-4 4" />);
export const AlertIcon = ({ size = 16 }: P) => svg(size, <><path d="M8 2 14.5 13.5h-13L8 2Z" /><path d="M8 6.5v3M8 11.5v.01" /></>);
export const ShieldIcon = ({ size = 16 }: P) => svg(size, <><path d="M8 1.5 13.5 3.5v4c0 3.5-2.4 6-5.5 7-3.1-1-5.5-3.5-5.5-7v-4L8 1.5Z" /><path d="m5.75 8 1.6 1.6 3-3.2" /></>);
