import { EffortItems, Menu, RepoItems, TopBar, type TopBarProps } from "./TopBar";
import { layout, Section, Specimen } from "./gallery/Section";
import styles from "./TopBar.gallery.module.css";

// The shell as the prototype draws it on galley, the sample repo.
const REPOS: TopBarProps["repos"] = [
  { name: "galley", meta: "3 efforts on the line", href: "#galley", current: true },
  { name: "madrigal", meta: "Connected today · no maps yet", href: "#madrigal" },
];
const EFFORT: NonNullable<TopBarProps["effort"]> = {
  name: "ACX compliance before delivery",
  efforts: [
    {
      name: "ACX compliance before delivery",
      meta: "Building · 2 of 9 landed · 2 building",
      glyph: "building",
      href: "#acx",
      current: true,
    },
    {
      name: "Per-chapter voice casting",
      meta: "Charting the way · 3 decided, 3 patches of fog",
      glyph: "building",
      href: "#casting",
    },
    {
      name: "Choosing the retail sample",
      meta: "Charting the way · one ticket left, in session with you",
      glyph: "ask",
      href: "#sample",
    },
  ],
  landed: [{ name: "Manuscript upload states", meta: "Landed 2 Sep · 6 tickets" }],
};
const BAR: TopBarProps = {
  repo: "galley",
  repos: REPOS,
  working: { count: 3, href: "#build" },
  needsYou: { count: 4, href: "#desk" },
};

export default function TopBarGallery() {
  return (
    <Section title="Top bar">
      <div className={layout.stack}>
        <Specimen name="topbar">
          <div className={layout.bar}>
            <TopBar {...BAR} />
          </div>
        </Specimen>
        <Specimen name="topbar-effort">
          <div className={layout.bar}>
            <TopBar {...BAR} effort={EFFORT} />
          </div>
        </Specimen>
        <Specimen name="topbar-nothing-waiting">
          <div className={layout.bar}>
            <TopBar {...BAR} effort={EFFORT} needsYou={{ count: 0, href: "#desk" }} />
          </div>
        </Specimen>
        <Specimen name="topbar-quiet">
          <div className={layout.bar}>
            <TopBar
              {...BAR}
              effort={EFFORT}
              working={{ count: 0, href: "#build" }}
              needsYou={{ count: 0, href: "#desk" }}
            />
          </div>
        </Specimen>
      </div>
      {/* Each switcher's menu, drawn open where it hangs beneath its button. */}
      <div className={layout.row}>
        <Specimen name="menu-repo">
          <div className={styles.menuBox}>
            <div className={styles.hang}>
              <Menu>
                <RepoItems repos={REPOS} />
              </Menu>
            </div>
          </div>
        </Specimen>
        <Specimen name="menu-effort">
          <div className={styles.menuBox}>
            <div className={styles.hang}>
              <Menu wide>
                <EffortItems efforts={EFFORT.efforts} landed={EFFORT.landed} />
              </Menu>
            </div>
          </div>
        </Specimen>
      </div>
    </Section>
  );
}
