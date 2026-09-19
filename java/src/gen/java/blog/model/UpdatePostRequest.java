package blog.model;


import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.annotation.JsonTypeName;



@JsonTypeName("UpdatePostRequest")
@jakarta.annotation.Generated(value = "org.openapitools.codegen.languages.JavaJAXRSSpecServerCodegen", comments = "Generator version: 7.25.0")
public class UpdatePostRequest   {
  private String title;
  private String body;
  private Boolean published;

  public UpdatePostRequest() {
  }

  /**
   **/
  public UpdatePostRequest title(String title) {
    this.title = title;
    return this;
  }

  
  @JsonProperty("title")
  public String getTitle() {
    return title;
  }

  @JsonProperty("title")
  public void setTitle(String title) {
    this.title = title;
  }

  /**
   **/
  public UpdatePostRequest body(String body) {
    this.body = body;
    return this;
  }

  
  @JsonProperty("body")
  public String getBody() {
    return body;
  }

  @JsonProperty("body")
  public void setBody(String body) {
    this.body = body;
  }

  /**
   **/
  public UpdatePostRequest published(Boolean published) {
    this.published = published;
    return this;
  }

  
  @JsonProperty("published")
  public Boolean getPublished() {
    return published;
  }

  @JsonProperty("published")
  public void setPublished(Boolean published) {
    this.published = published;
  }


  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    UpdatePostRequest updatePostRequest = (UpdatePostRequest) o;
    return Objects.equals(this.title, updatePostRequest.title) &&
        Objects.equals(this.body, updatePostRequest.body) &&
        Objects.equals(this.published, updatePostRequest.published);
  }

  @Override
  public int hashCode() {
    return Objects.hash(title, body, published);
  }

  @Override
  public String toString() {
    StringBuilder sb = new StringBuilder();
    sb.append("class UpdatePostRequest {\n");
    
    sb.append("    title: ").append(toIndentedString(title)).append("\n");
    sb.append("    body: ").append(toIndentedString(body)).append("\n");
    sb.append("    published: ").append(toIndentedString(published)).append("\n");
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
