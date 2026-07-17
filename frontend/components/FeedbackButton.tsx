const DEFAULT_FEEDBACK_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLSfEN-WbQOsJEmWNY7-hjZ8lwopknAreOcv9nU6np66zAuF1_Q/viewform";

const FEEDBACK_FORM_URL = process.env.NEXT_PUBLIC_FEEDBACK_FORM_URL ?? DEFAULT_FEEDBACK_FORM_URL;

export function FeedbackButton() {
  if (!FEEDBACK_FORM_URL) return null;

  return (
    <a
      href={FEEDBACK_FORM_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="feedback-fab"
      aria-label="피드백 남기기"
    >
      💬 피드백 남기기
    </a>
  );
}
