import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Icon from "../components/icons";
import Logo from "../components/Logo";

const FEATURES = [
  {
    icon: "package",
    title: "All orders in one place",
    text: "Stop juggling Messenger chats and notebooks. Every order is recorded, searchable, and organized.",
  },
  {
    icon: "link",
    title: "One link per customer",
    text: "Share a tracking link when you confirm an order. Customers check status themselves — zero repetitive questions.",
  },
  {
    icon: "truck",
    title: "Clear status workflow",
    text: "Placed, confirmed, shipped, delivered. Your customers always know exactly where their order stands.",
  },
  {
    icon: "phone",
    title: "Works on any phone",
    text: "Your customers open the tracking page on their phone — no app to install, no account to create.",
  },
];

const STEPS = [
  {
    title: "Create your account",
    text: "Sign up with your email and store name — takes 30 seconds.",
  },
  {
    title: "Add your orders",
    text: "Type in each order with the customer's name, phone, and items.",
  },
  {
    title: "Share the tracking link",
    text: "Customer opens the link and sees live status. You get your time back.",
  },
];

/** A small, honest product mock — a mini tracking card exactly like the real one. */
function TrackingMock() {
  return (
    <div className="hero-mock" aria-hidden="true">
      <div className="hero-mock-card">
        <div className="hero-mock-head">
          <span className="hero-mock-store">
            <span className="hero-mock-store-dot" />
            Abin Fashion House
          </span>
          <span className="hero-mock-order">Order #1024</span>
        </div>
        <div className="hero-mock-status hero-mock-status--shipped">
          <span className="hero-mock-status-dot" />
          Shipped — on the way to the customer
        </div>
        <div className="hero-mock-steps">
          <span className="hero-mock-step hero-mock-step--done" />
          <span className="hero-mock-step hero-mock-step--done" />
          <span className="hero-mock-step hero-mock-step--done" />
          <span className="hero-mock-step" />
        </div>
        <div className="hero-mock-foot">
          <span>Placed 10:24 AM</span>
          <span>Updated 2 hours ago</span>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { seller } = useAuth();

  return (
    <div className="landing">
      <header className="landing-header">
        <Logo size={30} withWordmark />
        <div className="landing-header-actions">
          {seller ? (
            <Link
              to={seller.role === "admin" ? "/admin" : "/dashboard"}
              className="button button--primary"
            >
              {seller.role === "admin" ? "Go to admin panel" : "Go to dashboard"}
            </Link>
          ) : (
            <>
              <Link to="/login" className="button button--ghost">
                Log in
              </Link>
              <Link to="/signup" className="button button--primary">
                Get started free
              </Link>
            </>
          )}
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h1>
            &ldquo;Order koi?&rdquo;
            <span className="hero-accent"> — ask no more.</span>
          </h1>
          <p className="hero-subtitle">
            OrderKoi gives online sellers a simple dashboard to manage orders —
            and gives customers a link to track their order themselves.
          </p>
          {!seller && (
            <div className="hero-actions">
              <Link to="/signup" className="button button--primary button--large">
                Create your free account
              </Link>
              <Link to="/login" className="button button--outline button--large">
                I already have an account
              </Link>
            </div>
          )}
          <p className="hero-hint">Free to start · Unlimited orders on Pro · No app needed</p>        </div>
        <TrackingMock />
      </section>

      <section className="features">
        <h2>Built for busy sellers</h2>
        <div className="features-grid">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="feature-card">
              <span className="feature-icon">
                <Icon name={feature.icon} size={22} />
              </span>
              <h3>{feature.title}</h3>
              <p>{feature.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="steps">
        <h2>How it works</h2>
        <ol className="steps-list">
          {STEPS.map((step, index) => (
            <li key={step.title} className="step">
              <span className="step-number">{index + 1}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="track-demo">
        <h2>What your customer sees</h2>
        <p className="track-demo-sub">
          One link, one page, zero questions. They watch the order move —
          you never have to answer &ldquo;order koi?&rdquo; again.
        </p>
        <TrackingMock />
      </section>

      <section className="landing-cta">
        <h2>Start tracking in minutes</h2>
        <p>Create your free account and log your first order today.</p>
        <Link to="/signup" className="button button--primary button--large">
          Create your free account
        </Link>
      </section>

      <footer className="landing-footer">
        <Logo size={24} withWordmark />
        <p>Order tracking for online sellers · Bangladesh 🇧🇩</p>
      </footer>
    </div>
  );
}
