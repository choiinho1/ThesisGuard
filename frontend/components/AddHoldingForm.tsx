"use client";

import { useState } from "react";
import type { CreateHoldingInput } from "@/types/schema";

const examples = ["AAPL", "MSFT", "AMZN", "GOOGL"];

export function AddHoldingForm({
  existingTickers,
  onSubmit,
}: {
  existingTickers: string[];
  onSubmit: (input: CreateHoldingInput) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [avgBuyPrice, setAvgBuyPrice] = useState("");
  const [targetWeight, setTargetWeight] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const normalizedTicker = ticker.trim().toUpperCase();
  const isDuplicateTicker = existingTickers.some(
    (item) => item.trim().toUpperCase() === normalizedTicker,
  );
  const duplicateError = isDuplicateTicker
    ? `${normalizedTicker}은(는) 이미 포트폴리오에 등록되어 있습니다.`
    : null;
  const canSubmit = normalizedTicker.length > 0
    && !isDuplicateTicker
    && Number(targetWeight) >= 0
    && Number(targetWeight) <= 100;

  const reset = () => {
    setTicker("");
    setCompanyName("");
    setQuantity("");
    setAvgBuyPrice("");
    setTargetWeight("");
    setFormError(null);
  };

  if (!open) {
    return (
      <button className="add-holding-trigger" onClick={() => setOpen(true)} type="button">
        <span className="add-icon">+</span>
        <span>
          <strong>새 종목 추가</strong>
          <small>종목을 먼저 추가한 뒤 투자 논리를 등록할 수 있습니다</small>
        </span>
        <span className="trigger-shortcut">TICKER →</span>
      </button>
    );
  }

  return (
    <section className="panel add-holding-panel">
      <div className="add-form-heading">
        <div>
          <span className="section-index">NEW</span>
          <h2>포트폴리오에 종목 추가</h2>
          <p>종목 정보를 먼저 등록하세요. 투자 논리는 종목 추가 후 별도로 입력합니다.</p>
        </div>
        <button className="close-button" onClick={() => setOpen(false)} type="button" aria-label="종목 추가 닫기">×</button>
      </div>

      <div className="ticker-entry">
        <label htmlFor="ticker">Ticker <span>필수</span></label>
        <div className="ticker-input-wrap">
          <input
            autoFocus
            id="ticker"
            maxLength={10}
            onChange={(event) => setTicker(event.target.value.replace(/[^a-zA-Z.\-]/g, "").toUpperCase())}
            placeholder="예: AAPL"
            value={ticker}
          />
          {normalizedTicker && <strong>{normalizedTicker}</strong>}
        </div>
        <div className="ticker-examples">
          <span>빠른 선택</span>
          {examples.map((item) => (
            <button key={item} onClick={() => setTicker(item)} type="button">{item}</button>
          ))}
        </div>
      </div>

      <div className="holding-fields">
        <Field label="회사명" placeholder="Apple Inc. (선택)" value={companyName} onChange={setCompanyName} />
        <Field label="보유 수량" min="0" placeholder="0" type="number" value={quantity} onChange={setQuantity} />
        <Field label="평균 매수가 ($)" min="0" placeholder="0.00" step="0.01" type="number" value={avgBuyPrice} onChange={setAvgBuyPrice} />
        <Field label="목표 비중 (%)" max="100" min="0" placeholder="10" step="0.1" type="number" value={targetWeight} onChange={setTargetWeight} />
      </div>

      {(duplicateError || formError) && (
        <div className="inline-error">{duplicateError || formError}</div>
      )}

      <div className="add-form-actions">
        <p>{normalizedTicker ? `${normalizedTicker}을(를) 포트폴리오에 추가합니다.` : "티커를 입력해 주세요."}</p>
        <div>
          <button className="secondary-button" onClick={() => { reset(); setOpen(false); }} type="button">취소</button>
          <button
            className="primary-button"
            disabled={!canSubmit || submitting}
            onClick={async () => {
              setSubmitting(true);
              setFormError(null);
              try {
                await onSubmit({
                  ticker: normalizedTicker,
                  company_name: companyName.trim() || normalizedTicker,
                  quantity: Number(quantity) || 0,
                  avg_buy_price: Number(avgBuyPrice) || 0,
                  target_weight: Number(targetWeight) || 0,
                });
                reset();
                setOpen(false);
              } catch (caught) {
                setFormError(caught instanceof Error ? caught.message : "종목을 추가하지 못했습니다.");
              } finally {
                setSubmitting(false);
              }
            }}
            type="button"
          >
            {submitting ? "추가하는 중…" : "종목 추가"}
          </button>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  onChange,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange"> & {
  label: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input {...props} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
