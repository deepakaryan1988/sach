import { useState } from 'react';
import ReactMarkdown from 'react-markdown';

export default function App() {
  const [inputQuery, setInputQuery] = useState("");
  const [claim, setClaim] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  const handleAnalyze = async () => {
    if (!inputQuery.trim()) return;
    setClaim(inputQuery);
    setAnalyzing(true);
    setResult(null);
    setError("");

    try {
      const response = await fetch("http://localhost:8000/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: inputQuery })
      });
      if (!response.ok) throw new Error("API Verification Failed");
      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "An error occurred during analysis.");
    } finally {
      setAnalyzing(false);
    }
  };

  const resetAnalysis = () => {
    setResult(null);
    setClaim("");
    setInputQuery("");
    setError("");
  };

  return (
    <div className="dark min-h-screen bg-surface text-on-surface font-body selection:bg-primary selection:text-on-primary-fixed overflow-x-hidden relative">
      
      {/* Decorative Gradients */}
      <div className="fixed top-0 left-0 w-full h-full pointer-events-none z-0 overflow-hidden">
        <div className="absolute -top-[10%] -left-[10%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full flex-shrink-0"></div>
        <div className="absolute top-[40%] -right-[10%] w-[50%] h-[50%] bg-error/5 blur-[120px] rounded-full flex-shrink-0"></div>
      </div>

      {/* TopAppBar */}
      <header className="fixed top-0 w-full z-50 bg-[#0c0e12]/60 backdrop-blur-2xl flex justify-between items-center px-6 py-4">
        <div className="flex items-center gap-4">
          <span className="material-symbols-outlined text-[#aaffdc] hover:opacity-70 transition-opacity cursor-pointer active:scale-95">menu</span>
          <h1 className="text-2xl font-headline font-bold tracking-[0.2em] text-[#aaffdc] uppercase">SACH</h1>
        </div>
        <div className="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center overflow-hidden border border-outline-variant/20">
            <span className="material-symbols-outlined text-outline">person</span>
        </div>
      </header>

      <main className="pt-24 pb-32 px-6 max-w-md mx-auto space-y-12 relative z-10 min-h-screen flex flex-col">
        
        {!claim && (
            <div className="flex-1 flex flex-col justify-center space-y-6">
                <h2 className="text-3xl font-headline font-bold text-on-surface">Enter a claim to verify</h2>
                <textarea 
                    value={inputQuery}
                    onChange={(e) => setInputQuery(e.target.value)}
                    placeholder="Paste a WhatsApp forward, news headline, or rumor here..."
                    className="w-full h-40 bg-surface-container-highest p-4 rounded-xl border border-transparent focus:border-primary/20 focus:outline-none focus:ring-4 focus:ring-primary/5 transition-all text-on-surface placeholder:text-outline-variant font-light resize-none"
                />
                <button 
                    onClick={handleAnalyze}
                    className="w-full py-5 bg-gradient-to-r from-primary to-primary-container text-on-primary-fixed font-headline font-bold text-sm tracking-[0.2em] uppercase rounded-xl flex items-center justify-center gap-3 active:scale-[0.98] transition-transform shadow-[0_0_30px_rgba(0,253,193,0.15)] hover:brightness-110"
                >
                    <span className="material-symbols-outlined text-lg">radar</span>
                    INITIATE ANALYSIS
                </button>
            </div>
        )}

        {analyzing && (
            <div className="flex-1 flex flex-col justify-center items-center space-y-8 animate-pulse text-center">
                <div className="relative flex items-center justify-center">
                    <div className="w-24 h-24 rounded-full border-2 border-primary/20 border-t-primary animate-spin"></div>
                    <span className="material-symbols-outlined text-4xl absolute text-primary">analytics</span>
                </div>
                <div className="space-y-2">
                    <h3 className="text-xl font-headline font-bold text-primary tracking-widest text-[#aaffdc]">ANALYSING</h3>
                    <p className="text-sm text-on-surface-variant max-w-[250px] mx-auto">Evaluating multi-agent consensus and mapping source contradictions...</p>
                </div>
            </div>
        )}

        {error && (
            <div className="flex-1 flex justify-center items-center">
                <div className="bg-error-container/30 text-error p-6 rounded-xl border border-error/50 w-full text-center">
                    <span className="material-symbols-outlined text-4xl mb-2">warning</span>
                    <p className="font-bold tracking-wider uppercase text-sm mb-1">Investigation Failed</p>
                    <p className="text-xs text-error/80">{error}</p>
                    <button onClick={resetAnalysis} className="mt-4 px-4 py-2 border border-error rounded-lg text-xs font-bold uppercase hover:bg-error/10">Return</button>
                </div>
            </div>
        )}

        {result && !analyzing && (
            <div className="space-y-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
                {/* User's Claim Section */}
                <section className="space-y-4">
                <label className="text-[10px] font-bold tracking-[0.2em] text-on-surface-variant uppercase">SUBMITTED CLAIM</label>
                <div className="glass-card p-6 rounded-xl border-l-2 border-primary/20">
                    <p className="text-lg leading-relaxed font-light italic text-on-surface/90">
                    "{claim}"
                    </p>
                </div>
                </section>

                {/* Truth Verdict Card */}
                <section className="relative py-8">
                <div className="flex flex-col items-start gap-2">
                    <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${result.truth_score > 0.7 ? 'bg-primary' : result.truth_score < 0.3 ? 'bg-error' : 'bg-secondary'} glow-dot`}></div>
                    <span className={`text-xs font-bold tracking-widest ${result.truth_score > 0.7 ? 'text-primary' : result.truth_score < 0.3 ? 'text-error' : 'text-secondary'} uppercase`}>Current Status</span>
                    </div>
                    <h2 className="text-5xl sm:text-6xl font-headline font-bold tracking-tighter text-on-surface leading-none mt-2 uppercase break-words hyphens-auto">
                    {result.verdict}
                    </h2>
                </div>
                <div className="absolute -right-12 top-0 -z-10 opacity-10">
                    <span className="material-symbols-outlined text-[150px]">
                        {result.truth_score > 0.7 ? 'verified_user' : result.truth_score < 0.3 ? 'gpp_bad' : 'help_center'}
                    </span>
                </div>
                </section>

                {/* Editorial Explanation */}
                <section className="space-y-6">
                <div className="space-y-4 max-w-[95%]">
                    <h3 className="text-xs font-bold tracking-[0.15em] text-on-surface-variant uppercase">Swarm Brain Breakdown</h3>
                    <div className="text-sm text-on-surface/90 leading-relaxed font-light [&>h3]:text-primary [&>h3]:text-xs [&>h3]:mt-6 [&>h3]:mb-2 [&>h3]:uppercase [&>h3]:tracking-widest [&>p]:mb-4 overflow-y-auto max-h-[300px] pr-2 border-l border-outline-variant/20 pl-4">
                       <ReactMarkdown>{result.explanation}</ReactMarkdown>
                    </div>
                </div>

                {/* Individual Model Insights */}
                {result.swarm_details && result.swarm_details.length > 0 && (
                  <div className="space-y-4">
                    <h3 className="text-xs font-bold tracking-[0.15em] text-on-surface-variant uppercase">Individual Model Consensus</h3>
                    <div className="grid grid-cols-1 gap-4">
                      {result.swarm_details.map((member: any, idx: number) => (
                        <div key={idx} className="bg-surface-container-low p-5 rounded-xl border border-outline-variant/10 space-y-2 hover:bg-surface-container-high transition-colors">
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] font-bold text-primary uppercase font-headline tracking-widest">{member.model_name}</span>
                            <div className="flex items-center gap-1">
                                <span className="text-[9px] text-on-surface-variant uppercase tracking-tighter">Score:</span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${member.truth_score > 0.7 ? 'bg-primary/20 text-primary' : member.truth_score < 0.3 ? 'bg-error/20 text-error' : 'bg-secondary/20 text-secondary'}`}>
                                {member.truth_score.toFixed(1)}
                                </span>
                            </div>
                          </div>
                          <p className="text-[11px] text-on-surface/70 leading-relaxed font-light italic">"{member.explanation}"</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-surface-container-low p-5 rounded-lg flex flex-col justify-between group border border-transparent hover:border-error/20 transition-colors">
                        <div className="space-y-1 mb-4">
                        <span className="block text-[10px] font-bold text-on-surface-variant uppercase tracking-tighter">Propaganda</span>
                        <span className="text-3xl font-headline font-bold text-error">{parseFloat(result.rhetoric_score || 0).toFixed(1)}</span>
                        </div>
                        <span className="material-symbols-outlined select-none text-error self-end" style={{ fontVariationSettings: "'FILL' 1" }}>warning</span>
                    </div>

                    <div className="bg-surface-container-low p-5 rounded-lg flex flex-col justify-between group border border-transparent hover:border-primary/20 transition-colors">
                        <div className="space-y-1 mb-4">
                        <span className="block text-[10px] font-bold text-on-surface-variant uppercase tracking-tighter">Swarm Agreement</span>
                        <span className="text-3xl font-headline font-bold text-primary">{(parseFloat(result.swarm_agreement || 0) * 100).toFixed(0)}%</span>
                        </div>
                        <span className="material-symbols-outlined select-none text-primary self-end" style={{ fontVariationSettings: "'FILL' 1" }}>hub</span>
                    </div>
                </div>
                </section>

                {/* Sources Section */}
                <section className="space-y-4">
                <h3 className="text-xs font-bold tracking-[0.15em] text-on-surface-variant uppercase">Evidence Base</h3>
                {result.sources && result.sources.length > 0 ? (
                    <div className="space-y-3">
                        {result.sources.map((src: any, idx: number) => {
                            const urlMatch = src.content.match(/URL:\s*(http[^\n]+)/);
                            const url = urlMatch ? urlMatch[1].trim() : "#";
                            const snippet = src.content.replace(/URL:.*?\nSnippet:\s*/, "");
                            return (
                                <a key={idx} href={url} target="_blank" rel="noreferrer" className="block p-4 bg-surface-container-high rounded-lg text-sm border-l-2 border-primary/40 hover:bg-surface-variant transition-colors group cursor-pointer">
                                    <span className="font-bold block text-primary mb-1 group-hover:underline">{src.title}</span>
                                    <span className="text-on-surface-variant text-xs line-clamp-2">{snippet}</span>
                                </a>
                            );
                        })}
                    </div>
                ) : (
                    <div className="py-12 border-y border-outline-variant/10 flex flex-col items-center justify-center text-center space-y-3">
                        <span className="material-symbols-outlined text-outline/30 text-4xl">database</span>
                        <p className="text-sm text-outline font-medium tracking-tight">0 Sources Found</p>
                        <p className="text-[10px] text-outline-variant uppercase tracking-widest">Cross-referencing failed</p>
                    </div>
                )}
                </section>

                {/* Bottom Spacer before CTA */}
                <div className="h-12"></div>

                {/* Bottom CTA */}
                <div className="fixed bottom-24 left-0 w-full px-6 z-40 bg-gradient-to-t from-surface pb-6 pt-4">
                <button onClick={resetAnalysis} className="w-full py-5 bg-gradient-to-r from-primary to-primary-container text-on-primary-fixed font-headline font-bold text-sm tracking-[0.2em] uppercase rounded-xl flex items-center justify-center gap-3 active:scale-[0.98] transition-transform shadow-[0_0_30px_rgba(0,253,193,0.15)] hover:brightness-110">
                    <span className="material-symbols-outlined text-lg">radar</span>
                    NEW ANALYSIS
                </button>
                </div>
            </div>
        )}
      </main>

      {/* BottomNavBar */}
      <nav className="fixed bottom-0 left-0 w-full bg-[#0c0e12]/80 backdrop-blur-3xl flex justify-around items-center pb-8 pt-4 px-2 z-50">
        <div className="flex flex-col items-center justify-center text-[#aaffdc] drop-shadow-[0_0_5px_rgba(170,255,220,0.4)] transition-colors cursor-pointer group">
          <span className="material-symbols-outlined mb-1 scale-110 duration-500 ease-out" style={{ fontVariationSettings: "'FILL' 1" }}>shield_with_heart</span>
          <span className="font-['Inter'] text-[10px] font-bold tracking-[0.15em]">VERIFY</span>
        </div>
        <div className="flex flex-col items-center justify-center text-slate-600 hover:text-[#aaffdc] transition-colors cursor-pointer group">
          <span className="material-symbols-outlined mb-1">database</span>
          <span className="font-['Inter'] text-[10px] font-bold tracking-[0.15em]">ARCHIVE</span>
        </div>
        <div className="flex flex-col items-center justify-center text-slate-600 hover:text-[#aaffdc] transition-colors cursor-pointer group">
          <span className="material-symbols-outlined mb-1">analytics</span>
          <span className="font-['Inter'] text-[10px] font-bold tracking-[0.15em]">TRENDS</span>
        </div>
        <div className="flex flex-col items-center justify-center text-slate-600 hover:text-[#aaffdc] transition-colors cursor-pointer group">
          <span className="material-symbols-outlined mb-1">person_outline</span>
          <span className="font-['Inter'] text-[10px] font-bold tracking-[0.15em]">PROFILE</span>
        </div>
      </nav>
    </div>
  );
}
