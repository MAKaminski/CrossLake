import Link from 'next/link';

export default function RunNotFound() {
  return (
    <>
      <h1>No such run</h1>
      <div className="empty">
        <p>That run id is not in the index.</p>
        <Link href="/">Back to all runs</Link>
      </div>
    </>
  );
}
