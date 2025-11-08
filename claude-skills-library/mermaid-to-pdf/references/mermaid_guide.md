# Mermaid Diagram Guide

This guide provides reference information for working with Mermaid diagrams.

## Supported Diagram Types

Mermaid supports a wide variety of diagram types. Below are the most commonly used:

### 1. Flowchart

```mermaid
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Process 1]
    B -->|No| D[Process 2]
    C --> E[End]
    D --> E
```

**Syntax**:
- `graph TD` - Top-down flowchart
- `graph LR` - Left-to-right flowchart
- `graph BT` - Bottom-to-top flowchart
- `graph RL` - Right-to-left flowchart

**Node shapes**:
- `A[Rectangle]` - Rectangle
- `B(Rounded)` - Rounded rectangle
- `C{Diamond}` - Diamond (decision)
- `D((Circle))` - Circle
- `E>Asymmetric]` - Asymmetric shape

### 2. Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant System
    participant Database

    User->>System: Login Request
    System->>Database: Query User
    Database-->>System: User Data
    System-->>User: Login Success
```

**Syntax**:
- `participant` - Define participants
- `->` - Solid line
- `-->` - Dashed line
- `->>` - Solid arrow
- `-->>` - Dashed arrow

### 3. Class Diagram

```mermaid
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +String breed
        +bark()
    }
    class Cat {
        +meow()
    }
    Animal <|-- Dog
    Animal <|-- Cat
```

**Relationships**:
- `<|--` - Inheritance
- `*--` - Composition
- `o--` - Aggregation
- `-->` - Association
- `--` - Link (solid)
- `..>` - Dependency

### 4. State Diagram

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Processing: Start
    Processing --> Success: Complete
    Processing --> Error: Fail
    Success --> [*]
    Error --> Idle: Retry
```

### 5. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains
    CUSTOMER {
        string name
        string email
        string phone
    }
    ORDER {
        int orderID
        date orderDate
        float total
    }
```

**Relationships**:
- `||--||` - One to one
- `||--o{` - One to many
- `}o--o{` - Many to many

### 6. Gantt Chart

```mermaid
gantt
    title Project Schedule
    dateFormat YYYY-MM-DD
    section Planning
    Requirements :done, req, 2024-01-01, 2024-01-15
    Design :active, des, 2024-01-16, 2024-01-30
    section Development
    Coding :dev, 2024-02-01, 30d
    Testing :test, after dev, 20d
```

### 7. Pie Chart

```mermaid
pie title Distribution
    "Category A" : 40
    "Category B" : 30
    "Category C" : 20
    "Category D" : 10
```

### 8. Git Graph

```mermaid
gitGraph
    commit
    commit
    branch develop
    checkout develop
    commit
    commit
    checkout main
    merge develop
    commit
```

### 9. Mindmap (v10.0+)

```mermaid
mindmap
  root((Project))
    Planning
      Requirements
      Design
    Development
      Frontend
      Backend
    Testing
      Unit Tests
      Integration Tests
```

### 10. Timeline (v10.0+)

```mermaid
timeline
    title History of Project
    2023 : Project Started
    2024 : Phase 1 Complete
         : Phase 2 Started
    2025 : Expected Completion
```

## Themes

Mermaid supports four built-in themes:

1. **default** - Standard theme with blue colors
2. **forest** - Green-based theme
3. **dark** - Dark background theme
4. **neutral** - Grayscale theme

Usage with scripts:
```bash
python mermaid_to_image.py input.mmd output.png --theme dark
python markdown_to_pdf.py input.md output.pdf --theme forest
```

## Configuration Options

### Image Format

- **PNG** - Raster format, good for web and documents
  - Pros: Wide compatibility, good quality
  - Cons: Fixed resolution, larger file size

- **SVG** - Vector format, scalable
  - Pros: Infinite scaling, smaller file size
  - Cons: Limited browser compatibility

### Background Color

Customize background color:
```bash
--background white
--background transparent
--background "#f0f0f0"
```

### Image Dimensions (PNG only)

```bash
--width 1200 --height 800
```

## Best Practices

### 1. Keep Diagrams Simple

- Limit nodes to 10-15 for readability
- Break complex diagrams into multiple smaller diagrams
- Use clear, concise labels

### 2. Use Consistent Naming

```mermaid
graph LR
    UserLogin[User Login] --> ValidateCredentials[Validate Credentials]
    ValidateCredentials --> CheckDatabase[Check Database]
```

### 3. Add Comments

```mermaid
graph TD
    %% This is a comment
    A[Start] --> B[Process]
```

### 4. Group Related Elements

```mermaid
graph TD
    subgraph Frontend
        A[UI] --> B[Components]
    end
    subgraph Backend
        C[API] --> D[Database]
    end
    B --> C
```

## Common Issues and Solutions

### Issue: Diagram Not Rendering

**Solutions**:
1. Check Mermaid syntax for errors
2. Ensure mermaid-cli or Playwright is installed
3. Verify code block formatting:
   ```markdown
   ```mermaid
   graph TD
       A --> B
   ```
   ```

### Issue: Text Overlapping

**Solutions**:
1. Increase image dimensions
2. Use shorter labels
3. Adjust diagram direction (TD vs LR)

### Issue: Poor Image Quality

**Solutions**:
1. Use PNG with higher resolution (--width 1600)
2. Or use SVG format for scalable quality
3. Ensure sufficient background padding

## Examples

### Example 1: System Architecture

```mermaid
graph TB
    subgraph Client
        Web[Web Browser]
        Mobile[Mobile App]
    end
    subgraph Server
        API[API Gateway]
        Auth[Auth Service]
        App[Application Server]
    end
    subgraph Data
        DB[(Database)]
        Cache[(Cache)]
    end
    Web --> API
    Mobile --> API
    API --> Auth
    API --> App
    App --> DB
    App --> Cache
```

### Example 2: User Journey

```mermaid
journey
    title User Registration Journey
    section Visit Website
      Browse: 5: User
      Click Register: 3: User
    section Fill Form
      Enter Details: 3: User
      Verify Email: 1: User, System
    section Complete
      Confirm: 5: User
      Welcome: 5: User, System
```

### Example 3: Database Schema

```mermaid
erDiagram
    USER ||--o{ ORDER : places
    USER {
        int userID PK
        string email
        string name
    }
    ORDER ||--|{ ORDER_ITEM : contains
    ORDER {
        int orderID PK
        int userID FK
        date orderDate
        decimal total
    }
    ORDER_ITEM {
        int itemID PK
        int orderID FK
        int productID FK
        int quantity
        decimal price
    }
    PRODUCT ||--o{ ORDER_ITEM : "ordered in"
    PRODUCT {
        int productID PK
        string name
        decimal price
        int stock
    }
```

## Resources

- [Mermaid Official Documentation](https://mermaid.js.org/)
- [Mermaid Live Editor](https://mermaid.live/)
- [Mermaid GitHub Repository](https://github.com/mermaid-js/mermaid)
