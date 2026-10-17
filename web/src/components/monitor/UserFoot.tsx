import { logout } from "@/app/login/actions";
import { initials } from "@/lib/auth/users";
import { LogoutIcon } from "@/components/icons";

export function UserFoot({ user }: { user: { name: string; role: string } }) {
  return (
    <form className="side-foot" action={logout}>
      <span className="avatar" aria-hidden="true">{initials(user.name)}</span>
      <span className="who">
        <b>{user.name}</b>
        <small>{user.role}</small>
      </span>
      <button type="submit" className="logout" title="Cerrar sesión">
        <LogoutIcon />
        <span>Cerrar sesión</span>
      </button>
    </form>
  );
}
