import { Frame, Pane, Split } from "./Frame";
import { layout, Section, Specimen } from "./gallery/Section";
import styles from "./Frame.gallery.module.css";

// Enough lines that a region overflows, so it can be seen to scroll on its own.
function Filler({ what }: { what: string }) {
  return Array.from({ length: 15 }, (_, i) => (
    <p key={i} style={{ padding: "4px 20px" }}>
      {`Line ${i + 1} of ${what}.`}
    </p>
  ));
}

// Stand-ins for the top bar and the route band, which are their own widgets.
function StandIn({ children }: { children: string }) {
  return (
    <p className="meta" style={{ padding: "12px 24px", borderBottom: "1px solid var(--border)" }}>
      {children}
    </p>
  );
}

export default function FrameGallery() {
  return (
    <Section title="Frames">
      <div className={layout.row}>
        <Specimen name="frame">
          <div className={styles.frame}>
            <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
              <Pane>
                <Filler what="the page" />
              </Pane>
            </Frame>
          </div>
        </Specimen>
        <Specimen name="frame-no-route">
          <div className={styles.frame}>
            <Frame bar={<StandIn>The top bar</StandIn>}>
              <Pane>
                <Filler what="the page" />
              </Pane>
            </Frame>
          </div>
        </Specimen>
        <Specimen name="split-left">
          <div className={styles.frame}>
            <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
              <Split left={{ label: "The queue", width: 240, children: <Filler what="the side" /> }}>
                <Filler what="the page" />
              </Split>
            </Frame>
          </div>
        </Specimen>
        <Specimen name="split-right">
          <div className={styles.frame}>
            <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
              <Split right={{ label: "The detail", width: 260, children: <Filler what="the side" /> }}>
                <Filler what="the page" />
              </Split>
            </Frame>
          </div>
        </Specimen>
      </div>
    </Section>
  );
}
