# Contributing to Blender Voice Command Add-on

## Team Structure
- Project Lead: Manveer Anand
- Team Members:
  - Member 1: Anshuman 
  - Member 2: Ayush Chaurasia 
  - Member 3: Pawan Meena 
  - Member 4: Kulidp Solanki 

## Development Workflow

### Branch Strategy
- `main`: Production-ready code (protected branch)
- `develop`: Integration branch for features (protected branch)
- `feature/*`: New features (e.g., feature/voice-recognition)
- `bugfix/*`: Bug fixes
- `release/*`: Release preparation
- `docs/*`: Documentation updates

### Getting Started
1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd blender_voice_addon
   ```
2. Create and activate virtual environment:
   ```bash
   python -m venv env
   source env/bin/activate  # Linux/Mac
   env\Scripts\activate     # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Making Changes
1. Update your develop branch:
   ```bash
   git checkout develop
   git pull origin develop
   ```
2. Create your feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Commit with meaningful messages:
   ```bash
   git commit -m "feat: add voice recognition module"
   ```

### Commit Message Format
- feat: New feature
- fix: Bug fix
- docs: Documentation changes
- style: Formatting, missing semicolons, etc.
- refactor: Code restructuring
- test: Adding tests
- chore: Maintenance tasks

### Pull Request Process
1. Update your feature branch with develop:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout feature/your-feature
   git rebase develop
   ```
2. Push your changes:
   ```bash
   git push origin feature/your-feature
   ```
3. Create Pull Request on GitHub
4. Require at least one review
5. Pass all tests
6. Resolve any conflicts

### Code Review Guidelines
- Review within 24 hours
- Be constructive and respectful
- Check for:
  - Code functionality
  - Error handling
  - Documentation
  - Test coverage

## Project Structure 