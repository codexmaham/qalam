import { Link } from "react-router-dom";

const STEPS = [
  {
    n: "1",
    title: "Speak",
    text: "A teacher or a student talks. A lesson, a list, a story, a correction.",
  },
  {
    n: "2",
    title: "Transcribe here",
    text: "Whisper, via whisper.cpp, will run on this computer. The audio does not get uploaded.",
  },
  {
    n: "3",
    title: "See it handwritten",
    text: "The same notebook renderer that powers Notes writes the page, ready to print.",
  },
];

export function VoicePage() {
  return (
    <main className="voice">
      <section className="voice-card">
        <p className="eyebrow">Next step</p>
        <h1>Voice to handwriting</h1>
        <p className="lede">
          Speak a lesson. Qalam will write it into the notebook. This page is the place that
          recording will land. The engine is not wired up yet.
        </p>
        <button className="mic" type="button" disabled>
          <span className="mic-dot" />
          Microphone
          <em>Coming with Whisper</em>
        </button>
        <ol className="steps">
          {STEPS.map((step) => (
            <li key={step.n}>
              <span>{step.n}</span>
              <div>
                <strong>{step.title}</strong>
                <p>{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
        <Link className="text-link" to="/">
          Try it with typed text
        </Link>
      </section>
    </main>
  );
}
