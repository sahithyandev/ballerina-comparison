package blog.model;


import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.annotation.JsonTypeName;



@JsonTypeName("RegisterRequest")
@jakarta.annotation.Generated(value = "org.openapitools.codegen.languages.JavaJAXRSSpecServerCodegen", comments = "Generator version: 7.25.0")
public class RegisterRequest   {
  private String username;
  private String email;
  private String password;

  public RegisterRequest() {
  }

  @JsonCreator
  public RegisterRequest(
    @JsonProperty(required = true, value = "username") String username,
    @JsonProperty(required = true, value = "email") String email,
    @JsonProperty(required = true, value = "password") String password
  ) {
    this.username = username;
    this.email = email;
    this.password = password;
  }

  /**
   **/
  public RegisterRequest username(String username) {
    this.username = username;
    return this;
  }

  
  @JsonProperty(required = true, value = "username")
  public String getUsername() {
    return username;
  }

  @JsonProperty(required = true, value = "username")
  public void setUsername(String username) {
    this.username = username;
  }

  /**
   **/
  public RegisterRequest email(String email) {
    this.email = email;
    return this;
  }

  
  @JsonProperty(required = true, value = "email")
  public String getEmail() {
    return email;
  }

  @JsonProperty(required = true, value = "email")
  public void setEmail(String email) {
    this.email = email;
  }

  /**
   **/
  public RegisterRequest password(String password) {
    this.password = password;
    return this;
  }

  
  @JsonProperty(required = true, value = "password")
  public String getPassword() {
    return password;
  }

  @JsonProperty(required = true, value = "password")
  public void setPassword(String password) {
    this.password = password;
  }


  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    RegisterRequest registerRequest = (RegisterRequest) o;
    return Objects.equals(this.username, registerRequest.username) &&
        Objects.equals(this.email, registerRequest.email) &&
        Objects.equals(this.password, registerRequest.password);
  }

  @Override
  public int hashCode() {
    return Objects.hash(username, email, password);
  }

  @Override
  public String toString() {
    StringBuilder sb = new StringBuilder();
    sb.append("class RegisterRequest {\n");
    
    sb.append("    username: ").append(toIndentedString(username)).append("\n");
    sb.append("    email: ").append(toIndentedString(email)).append("\n");
    sb.append("    password: ").append(toIndentedString(password)).append("\n");
    sb.append("}");
    return sb.toString();
  }

  /**
   * Convert the given object to string with each line indented by 4 spaces
   * (except the first line).
   */
  private String toIndentedString(Object o) {
    return o == null ? "null" : o.toString().replace("\n", "\n    ");
  }


}
