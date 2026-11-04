
import { useState, useRef } from "react";
import {
  ArrowRight,
  BookOpen,
  Leaf,
  LoaderCircle,
  Sparkles,
  Search,
  RotateCcw,
  ImagePlus,
  X,
} from "lucide-react";
import "./App.css";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const suggestions = [
  "Something melancholic and introspective, with beautiful prose",
  "A philosophical journey that makes me question life",
  "A cozy, comforting story with a little humour",
  "Dark academia, mystery, and psychological tension",
];

function App() {
  const [query, setQuery] = useState("");
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const fileInputRef = useRef(null);

  async function handleSubmit(event) {
    event.preventDefault();

    if (!query.trim() && !selectedImage) {
      setError("Describe your reading mood or upload an image.");
      return;
    }

    setLoading(true);
    setError("");
    setHasSearched(true);
    setRecommendations([]);

    try {
      const formData = new FormData();

      if (query.trim()) {
        formData.append("query", query.trim());
      }

      if (selectedImage) {
        formData.append("image", selectedImage);
      }

      formData.append("top_k", "10");

      const response = await fetch(`${API_BASE}/api/recommend`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));

        throw new Error(
          body.detail || `Request failed with status ${response.status}`
        );
      }

      const data = await response.json();
      const results = data.recommendations ?? data.results ?? [];

      if (!Array.isArray(results)) {
        throw new Error("Unexpected response from recommendation API.");
      }

      setRecommendations(results);
    } catch (err) {
      setError(err.message || "Unable to fetch recommendations.");
    } finally {
      setLoading(false);
    }
  }

  function handleImageChange(event) {
  const file = event.target.files?.[0];

  if (!file) return;

  const allowedTypes = [
    "image/jpeg",
    "image/png",
    "image/webp",
  ];

  if (!allowedTypes.includes(file.type)) {
    setError("Please upload a JPEG, PNG, or WEBP image.");
    event.target.value = "";
    return;
  }

  if (file.size > 5 * 1024 * 1024) {
    setError("Image must be 5 MB or smaller.");
    event.target.value = "";
    return;
  }

  setError("");
  setSelectedImage(file);
}

function removeImage() {
  setSelectedImage(null);

  if (fileInputRef.current) {
    fileInputRef.current.value = "";
  }
}

  function resetSearch() {
  setQuery("");
  setSelectedImage(null);

  if (fileInputRef.current) {
    fileInputRef.current.value = "";
  }

  setRecommendations([]);
  setError("");
  setHasSearched(false);
}

  return (
    <div className="app-shell">
      <header className="navbar">
        <a href="#" className="brand" onClick={resetSearch}>
          <span className="brand-mark">
            <Leaf size={20} />
          </span>
          <span>nextleaf</span>
        </a>

        <div className="navbar-caption">
          A different way to discover books
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="eyebrow">
            <Sparkles size={14} />
            <span>BOOKS THAT RESONATE WITH YOU</span>
          </div>

          <h1>
            Find a book for
            <br />
            <span>where you are.</span>
          </h1>

          <p className="hero-description">
            Sometimes you don't know what you want to read.
            You only know how you want to feel.
            Tell us what's on your mind. We'll find the story.
          </p>

          <form className="search-panel" onSubmit={handleSubmit}>
            <div className="input-heading">
              <span>WHAT ARE YOU IN THE MOOD FOR?</span>
              <span className="optional-label">DESCRIBE IT FREELY</span>
            </div>

            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="I'm looking for something melancholic and introspective, with beautiful prose. Something that explores loneliness but leaves me with a little hope..."
              rows={5}
              disabled={loading}
            />

            <div className="image-upload-area">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handleImageChange}
                hidden
                disabled={loading}
              />

              {!selectedImage ? (
                <button
                  type="button"
                  className="image-upload-button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading}
                >
                  <ImagePlus size={16} />
                  Add image
                </button>
              ) : (
                <div className="selected-image">
                  <ImagePlus size={16} />
                  <span>{selectedImage.name}</span>

                  <button
                    type="button"
                    onClick={removeImage}
                    disabled={loading}
                    aria-label="Remove image"
                  >
                    <X size={15} />
                  </button>
                </div>
              )}

              <span className="image-upload-hint">
                Describe your mood, upload an image, or use both.
              </span>
            </div>

            <div className="search-bottom">
              <span className="input-hint">
                There are no right or wrong answers.
              </span>

              <button type="submit" className="search-button" disabled={loading}>
                {loading ? (
                  <>
                    <LoaderCircle size={17} className="spin" />
                    Finding books
                  </>
                ) : (
                  <>
                    Find my books
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </div>
          </form>

          {!hasSearched && (
            <div className="suggestions">
              <span className="suggestions-label">NOT SURE WHERE TO START?</span>

              <div className="suggestion-list">
                {suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setQuery(item)}
                    disabled={loading}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              <span>{error}</span>
            </div>
          )}
        </section>

        {loading && (
          <section className="loading-state">
            <div className="loading-symbol">
              <BookOpen size={25} />
            </div>
            <h2>Looking for your next story...</h2>
            <p>Exploring themes, atmosphere, and reading experiences.</p>
          </section>
        )}

        {!loading && hasSearched && recommendations.length > 0 && (
          <section className="results-section">
            <div className="results-header">
              <div>
                <div className="eyebrow results-eyebrow">
                  <Sparkles size={14} />
                  YOUR PERSONAL READING LIST
                </div>

                <h2>Stories worth discovering.</h2>

                <p>
                  {recommendations.length} books selected around your reading mood.
                </p>
              </div>

              <button className="new-search-button" onClick={resetSearch}>
                <RotateCcw size={15} />
                New search
              </button>
            </div>

            <div className="book-grid">
              {recommendations.map((book, index) => {
                const themes = Array.isArray(book.themes)
                  ? book.themes
                  : typeof book.themes === "string"
                    ? (() => {
                        try {
                          return JSON.parse(book.themes);
                        } catch {
                          return [];
                        }
                      })()
                    : [];

                return (
                  <article
                    className="book-card"
                    key={
                      book.work_id ??
                      book.representative_book_id ??
                      index
                    }
                  >
                    <div className="card-topline">
                      <span className="book-index">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="card-decoration">
                        <BookOpen size={17} />
                      </span>
                    </div>

                    <h3>{book.title || "Untitled"}</h3>

                    <p className="book-author">
                      {book.author_names || "Unknown author"}
                    </p>

                    {book.reading_experience && (
                      <div className="experience">
                        <p>{book.reading_experience}</p>
                      </div>
                    )}

                    {book.blurb && (
                      <p className="book-blurb">{book.blurb}</p>
                    )}

                    {themes.length > 0 && (
                      <div className="theme-list">
                        {themes.slice(0, 4).map((theme, i) => (
                          <span key={`${theme}-${i}`}>{theme}</span>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>

            <div className="results-footer">
              <span>
                <Leaf size={15} />
                Every story finds its reader.
              </span>

              <button onClick={resetSearch}>
                Explore another mood <ArrowRight size={15} />
              </button>
            </div>
          </section>
        )}

        {!loading && hasSearched && recommendations.length === 0 && !error && (
          <section className="empty-state">
            <BookOpen size={30} />
            <h2>No stories found this time.</h2>
            <p>Try describing your reading mood a little differently.</p>
            <button className="search-button" onClick={resetSearch}>
              Try another search <ArrowRight size={16} />
            </button>
          </section>
        )}
      </main>

      <footer className="footer">
        <div className="footer-brand">
          <Leaf size={15} />
          nextleaf
        </div>
        <span>Find stories that feel like you.</span>
      </footer>
    </div>
  );
}

export default App;
