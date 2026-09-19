package blog.model;


import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.annotation.JsonTypeName;



@JsonTypeName("CreateCommentRequest")
@jakarta.annotation.Generated(value = "org.openapitools.codegen.languages.JavaJAXRSSpecServerCodegen", comments = "Generator version: 7.25.0")
public class CreateCommentRequest   {
  private String body;

  public CreateCommentRequest() {
  }

  @JsonCreator
  public CreateCommentRequest(
    @JsonProperty(required = true, value = "body") String body
  ) {
    this.body = body;
  }

  /**
   **/
  public CreateCommentRequest body(String body) {
    this.body = body;
    return this;
  }

  
  @JsonProperty(required = true, value = "body")
  public String getBody() {
    return body;
  }

  @JsonProperty(required = true, value = "body")
  public void setBody(String body) {
    this.body = body;
  }


  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    CreateCommentRequest createCommentRequest = (CreateCommentRequest) o;
    return Objects.equals(this.body, createCommentRequest.body);
  }

  @Override
  public int hashCode() {
    return Objects.hash(body);
  }

  @Override
  public String toString() {
    StringBuilder sb = new StringBuilder();
    sb.append("class CreateCommentRequest {\n");
    
    sb.append("    body: ").append(toIndentedString(body)).append("\n");
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
