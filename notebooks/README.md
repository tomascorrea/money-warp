# Money-Warp Interactive Notebooks

This directory contains interactive Jupyter notebooks that demonstrate the capabilities of the money-warp library through hands-on, visual interfaces.

## Available Notebooks

### 📊 Interactive Loan Visualization (`interactive_loan_visualization.ipynb`)

A comprehensive interactive interface for creating loans, recording payments, and visualizing loan behavior over time.

**Features:**
- 📋 **Loan Creation Form**: Interactive widgets for all loan parameters
- 💰 **Payment Recording**: Add payments and see real-time balance updates  
- ⏰ **Time Machine**: Travel through time to see loan state at any point
- 📊 **Interactive Charts**: Balance evolution, payment breakdown, and cash flow visualization
- 🚨 **Late Payment Fines**: Automatic fine calculation with configurable grace periods

**Key Capabilities:**
- Create loans with custom parameters (principal, interest rate, payment schedule)
- Record payments with automatic allocation (Fines → Interest → Principal)
- Use time machine (Warp) to analyze loan state at any historical point
- Visualize balance changes over time with interactive Plotly charts
- Experiment with late payment scenarios and fine calculations
- Explore "what-if" scenarios with different payment strategies

## Getting Started

### Prerequisites

Make sure you have the notebook dependencies installed:

```bash
# Install notebook dependencies (if not already installed)
poetry install --with notebook
```

### Running the Notebooks

1. **Start Jupyter Lab:**
   ```bash
   poetry run jupyter lab
   ```

2. **Navigate to the notebooks directory**

3. **Open `interactive_loan_visualization.ipynb`**

4. **Run all cells** to initialize the interactive interface

5. **Start exploring!** Create a loan, record payments, and use the time machine

## Usage Examples

### Basic Workflow
1. **Create a Loan**: Use the form to set up a loan with your desired parameters
2. **Record Payments**: Add payments to see their impact on the balance
3. **Time Travel**: Use the slider to see the loan state at different points in time
4. **Analyze**: Watch the charts update in real-time as you make changes

### Interesting Scenarios to Try
- **Perfect Borrower**: Make all payments on time and see the expected amortization
- **Late Payment Impact**: Make a payment late to see fine calculation and impact
- **Early Payoff**: Make extra payments to see interest savings
- **Grace Period Testing**: Experiment with different grace periods
- **Time Machine Analysis**: Go back in time to see historical loan states

## Technical Details

### Dependencies
- **money-warp**: Core loan modeling library
- **ipywidgets**: Interactive form controls
- **plotly**: Interactive charting
- **pandas**: Data manipulation
- **jupyter**: Notebook environment

### Architecture
The notebook uses a clean separation of concerns:
- **State Management**: Global variables track loan state and time position
- **UI Components**: Jupyter widgets provide interactive controls
- **Business Logic**: money-warp library handles all loan calculations
- **Visualization**: Plotly creates interactive charts with real-time updates
- **Time Travel**: Warp context manager enables historical analysis

### Performance
The notebook is optimized for interactive use:
- Efficient chart updates using Plotly's incremental rendering
- Lazy evaluation of expensive calculations
- Responsive UI with immediate feedback
- Memory-efficient time series generation

## Educational Value

This notebook is perfect for:
- **Financial Education**: Understanding loan mechanics and payment allocation
- **Scenario Analysis**: Exploring different payment strategies
- **Risk Assessment**: Seeing the impact of late payments and fines
- **Time-based Analysis**: Understanding how loans evolve over time
- **Interactive Learning**: Hands-on exploration of financial concepts

## Contributing

To add new notebooks or improve existing ones:

1. Follow the existing code structure and patterns
2. Use clear, descriptive variable names
3. Add comprehensive documentation and examples
4. Test with various loan scenarios
5. Ensure responsive performance with reasonable data sizes

---

**Happy Exploring!** 🚀

The interactive notebooks provide a powerful way to understand and analyze loan behavior through hands-on experimentation and visualization.
