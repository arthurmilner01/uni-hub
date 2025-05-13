import { useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";

// Component for user registration
const RegisterPage = () => {
  const [formData, setFormData] = useState({
    first_name: "",
    last_name: "",
    dob: "",
    address: "",
    postcode: "",
    email: "",
    password: "",
    confirm_password: "",
  });
  const [errors, setErrors] = useState({}); // Store multiple errors
  const [success, setSuccess] = useState(false);

  // Handle input changes
  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrors({});
    setSuccess(false);

    // Check if passwords match
    if (formData.password !== formData.confirm_password) {
      setErrors({ confirm_password: "Passwords do not match" });
      return;
    }

    try {
      // Send registration data
      await axios.post("http://localhost:8000/auth/users/", {
        first_name: formData.first_name,
        last_name: formData.last_name,
        dob: formData.dob,
        address: formData.address,
        postcode: formData.postcode,
        email: formData.email,
        password: formData.password,
      });
      setSuccess(true);
    } catch (err) {
      // Handle validation or network errors
      if (err.response && err.response.data) {
        setErrors(err.response.data);
      } else {
        setErrors({ general: "Registration failed. Please try again." });
      }
    }
  };

  return (
    <div className="container mt-5">
      <div className="row justify-content-center">
        <div className="col-md-6">
          <div className="card">
            <div className="card-body">
              <h2 className="text-center mb-4">Register</h2>
              
              {success && (
                <div className="alert alert-success">
                  Account created! Check your email to activate.
                </div>
              )}

              {errors.general && (
                <div className="alert alert-danger">{errors.general}</div>
              )}

              <form onSubmit={handleSubmit}>
                <div className="mb-3">
                  <label className="form-label">First Name</label>
                  <input
                    type="text"
                    className="form-control"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleChange}
                    required
                  />
                  {errors.first_name && (
                    <small className="text-danger">{errors.first_name}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Last Name</label>
                  <input
                    type="text"
                    className="form-control"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleChange}
                    required
                  />
                  {errors.last_name && (
                    <small className="text-danger">{errors.last_name}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Date of Birth</label>
                  <input
                    type="date"
                    className="form-control"
                    name="dob"
                    value={formData.dob}
                    onChange={handleChange}
                    required
                  />
                  {errors.dob && (
                    <small className="text-danger">{errors.dob}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Address</label>
                  <input
                    type="text"
                    className="form-control"
                    name="address"
                    value={formData.address}
                    onChange={handleChange}
                    required
                  />
                  {errors.address && (
                    <small className="text-danger">{errors.address}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Postcode</label>
                  <input
                    type="text"
                    className="form-control"
                    name="postcode"
                    value={formData.postcode}
                    onChange={handleChange}
                    required
                  />
                  {errors.postcode && (
                    <small className="text-danger">{errors.postcode}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Email</label>
                  <input
                    type="email"
                    className="form-control"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    required
                  />
                  {errors.email && (
                    <small className="text-danger">{errors.email}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Password</label>
                  <input
                    type="password"
                    className="form-control"
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    required
                  />
                  {errors.password && (
                    <small className="text-danger">{errors.password}</small>
                  )}
                </div>

                <div className="mb-3">
                  <label className="form-label">Confirm Password</label>
                  <input
                    type="password"
                    className="form-control"
                    name="confirm_password"
                    value={formData.confirm_password}
                    onChange={handleChange}
                    required
                  />
                  {errors.confirm_password && (
                    <small className="text-danger">
                      {errors.confirm_password}
                    </small>
                  )}
                </div>

                <button type="submit" className="btn btn-info text-white w-100">
                  Register
                </button>
              </form>

              <div className="mt-3 text-center">
                <p>
                  Already have an account?
                  <Link
                    to="/login"
                    className="text-primary"
                    style={{ marginLeft: "5px" }}
                  >
                    Login here.
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
