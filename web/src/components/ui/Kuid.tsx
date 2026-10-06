const KUID = /(KA-[A-Z]{2}-[A-Z]{2}-[A-Z]{3}-\d{4}-\d{6})/;

/**
 * Running text with every KUID in it kept on one line. An ID broken at a dash
 * gets copied down as two things.
 */
export function WithKuids({ text }: { text: string }) {
  return (
    <>
      {text.split(KUID).map((part, i) =>
        KUID.test(part) ? (
          <span key={i} className="whitespace-nowrap font-mono">{part}</span>
        ) : (
          part
        ),
      )}
    </>
  );
}
