// A ticket's acceptance criteria, as written in the ticket and read-only. Nothing
// ticks a criterion in this slice, so there is no mark, no count and no test
// named beneath it (#70); the prototype's tick boxes are not ported.
export function Criteria({ criteria }: { criteria: string[] }) {
  return (
    <ul className="crit">
      {criteria.map((criterion, i) => (
        // Keyed by place: a ticket's criteria are its body's lines in order, and
        // two may read alike.
        <li key={i}>
          <span className="c-text">{criterion}</span>
        </li>
      ))}
    </ul>
  );
}
