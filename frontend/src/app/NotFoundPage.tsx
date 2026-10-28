import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="mx-auto grid max-w-xl gap-3 py-16 text-center">
      <h1 className="font-display text-2xl font-semibold">Stranica ne postoji</h1>
      <p className="text-muted">Poveznica je možda zastarjela.</p>
      <Link to="/" className="text-accent underline-offset-4 hover:underline">
        Natrag na početak
      </Link>
    </div>
  );
}
