package blog.model;


import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.annotation.JsonTypeName;



@JsonTypeName("CreatePostRequest")
@jakarta.annotation.Generated(value = "org.openapitools.codegen.languages.JavaJAXRSSpecServerCodegen", comments = "Generator version: 7.25.0")
public class CreatePostRequest   {
  private String title;
  private String body;
  private Boolean published = false;

  public CreatePostRequest() {
  }

  @JsonCreator
  public CreatePostRequest(
    @JsonProperty(required = true, value = "title") String title,
    @JsonProperty(required = true, value = "body") String body
  ) {
    this.title = title;
    this.body = body;
  }

  /**
   **/
  public CreatePostRequest title(String title) {
    this.title = title;
    return this;
  }

  
  @JsonProperty(required = true, value = "title")
  public String getTitle() {
    return title;
  }

  @JsonProperty(required = true, value = "title")
  public void setTitle(String title) {
    this.title = title;
  }

  /**
   **/
  public CreatePostRequest body(String body) {
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

  /**
   **/
  public CreatePostRequest published(Boolean published) {
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
    CreatePostRequest createPostRequest = (CreatePostRequest) o;
    return Objects.equals(this.title, createPostRequest.title) &&
        Objects.equals(this.body, createPostRequest.body) &&
        Objects.equals(this.published, createPostRequest.published);
  }

  @Override
  public int hashCode() {
    return Objects.hash(title, body, published);
  }

  @Override
  public String toString() {
    StringBuilder sb = new StringBuilder();
    sb.append("class CreatePostRequest {\n");
    
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
