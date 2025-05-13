import React, { useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

// Component for creating a new community
const CreateCommunityPage = () => {
  const [communityName, setCommunityName] = useState("");
  const [description, setDescription] = useState("");
  const [rules, setRules] = useState("");
  const [privacy, setPrivacy] = useState("public");
  const [keywords, setKeywords] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const navigate = useNavigate();
  const { accessToken } = useAuth();

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    try {
      // Convert keywords string to array
      const keywordsArray = keywords
        ? keywords.split(",").map((kw) => kw.trim())
        : [];

      const data = {
        community_name: communityName,
        description,
        rules,
        privacy,
        keywords: keywordsArray,
      };

      const headers = accessToken
        ? { Authorization: `Bearer ${accessToken}` }
        : {};

      // Send POST request to create community
      const response = await axios.post("http://localhost:8000/api/communities/", data, {
        headers,
        withCredentials: true,
      });

      // If successful, show success message and redirect
      if (response.status === 201 || response.status === 200) {
        setSuccess("Community created successfully!");
        setTimeout(() => {
          navigate(`/communities/${response.data.id}`);
        }, 2000);
      }
    } catch (err) {
      console.error("Error creating community:", err.response ? err.response.data : err);
      setError("Error creating community. Please try again.");
    }
  };

  return (
    <div className="container mt-5">
      <div className="row justify-content-center">
        <div className="col-md-8 col-lg-6">
          <div className="card shadow-sm">
            <div className="card-body">
              <h3 className="card-title text-center mb-4">Create Community</h3>
              {error && <div className="alert alert-danger">{error}</div>}
              {success && <div className="alert alert-success">{success}</div>}

              <form onSubmit={handleSubmit}>
                <div className="mb-3">
                  <label className="form-label">Community Name:</label>
                  <input
                    type="text"
                    className="form-control"
                    value={communityName}
                    onChange={(e) => setCommunityName(e.target.value)}
                    required
                  />
                </div>

                <div className="mb-3">
                  <label className="form-label">Description:</label>
                  <textarea
                    className="form-control"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    required
                  />
                </div>

                <div className="mb-3">
                  <label className="form-label">Rules:</label>
                  <textarea
                    className="form-control"
                    value={rules}
                    onChange={(e) => setRules(e.target.value)}
                    rows={3}
                  />
                </div>

                <div className="mb-3">
                  <label className="form-label">Privacy:</label>
                  <select
                    className="form-select"
                    value={privacy}
                    onChange={(e) => setPrivacy(e.target.value)}
                  >
                    <option value="public">Public</option>
                    <option value="private">Private</option>
                  </select>
                </div>

                {/* Input for keywords */}
                <div className="mb-3">
                  <label className="form-label">Keywords (comma-separated):</label>
                  <input
                    type="text"
                    className="form-control"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                  />
                  <small className="text-muted">
                    e.g. "Electronics, UWE, Coding"
                  </small>
                </div>

                <button type="submit" className="btn btn-info text-white w-100">
                  Create Community
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateCommunityPage;
