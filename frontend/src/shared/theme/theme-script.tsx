import Script from "next/script";

export function ThemeScript() {
  const script = `
(function(){
  var key='govdecl-theme';
  var stored=localStorage.getItem(key);
  var theme=stored || 'dark';
  document.documentElement.dataset.theme=theme;
  document.documentElement.classList.toggle('dark', theme === 'dark');
})();`;
  return (
    <Script
      id="govdecl-theme-script"
      strategy="afterInteractive"
      dangerouslySetInnerHTML={{ __html: script }}
    />
  );
}
