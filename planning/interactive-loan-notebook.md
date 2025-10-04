# Interactive Loan Visualization Notebook - Planning Document

## Overview

Create an interactive Jupyter notebook that provides a comprehensive interface for:
1. **Loan Creation**: Form-based loan parameter input
2. **Payment Management**: Dynamic payment recording with real-time updates
3. **Time Machine**: Slider-controlled time travel using Warp functionality
4. **Balance Visualization**: Interactive charts showing loan evolution over time

## Technical Stack

### Core Dependencies
- **money-warp**: Our existing loan library with Warp time machine
- **ipywidgets**: Interactive form elements and controls
- **plotly**: Interactive charting and visualization
- **pandas**: Data manipulation and time series handling
- **datetime**: Date handling and calculations

### Notebook Structure

```
Interactive Loan Visualization
├── Section 1: Setup & Imports
├── Section 2: Loan Creation Form
├── Section 3: Payment Recording Interface  
├── Section 4: Time Machine Control
├── Section 5: Interactive Visualizations
└── Section 6: Summary & Analysis
```

## Detailed Implementation Plan

### Section 1: Setup & Imports
**Purpose**: Initialize environment and define utility functions

**Components**:
- Import all required libraries
- Define formatting functions for money display
- Set up Plotly styling and themes
- Create helper functions for date calculations

**Key Functions**:
```python
def format_money(amount: Money) -> str
def calculate_payment_dates(start_date, num_payments, frequency)
def setup_plotly_theme()
```

### Section 2: Loan Creation Form
**Purpose**: Interactive form for loan parameter input

**Widgets Required**:
- `FloatText`: Principal amount ($10,000 default)
- `Text`: Interest rate ("5% annual" default)
- `Dropdown`: Payment frequency (Monthly, Quarterly, etc.)
- `IntSlider`: Number of payments (1-60, default 12)
- `DatePicker`: Loan start date (default today)
- `FloatSlider`: Late fee rate (0-10%, default 2%)
- `IntSlider`: Grace period days (0-30, default 0)
- `Button`: "Create Loan" button

**Output Display**:
- Loan summary box with key parameters
- Amortization schedule table (first 5 rows + expandable)
- Expected total payments and interest

**Validation**:
- Principal > 0
- Interest rate parseable by InterestRate class
- Valid date selections
- Reasonable parameter ranges

### Section 3: Payment Recording Interface
**Purpose**: Dynamic payment addition with real-time loan updates

**Widgets Required**:
- `FloatText`: Payment amount
- `DatePicker`: Payment date
- `Text`: Optional payment description
- `Button`: "Record Payment" button
- `Button`: "Clear All Payments" button

**Display Components**:
- Payment history table with allocation breakdown
- Current balance display (prominent)
- Outstanding fines indicator
- Payment allocation summary (Fines → Interest → Principal)

**Real-time Updates**:
- Balance recalculation after each payment
- Fine calculation and application
- Chart updates (triggered automatically)

### Section 4: Time Machine Control
**Purpose**: Warp functionality with slider interface

**Widgets Required**:
- `SelectionRangeSlider`: Date range from loan start to end + 5 periods
- `DatePicker`: Specific date selector (alternative to slider)
- `Button`: "Warp to Date" button
- `Button`: "Return to Present" button
- `HTML`: Current warped date display

**Time Range Calculation**:
- Start: Loan disbursement date
- End: Final payment date + 5 payment periods
- Default: Current date (present time)

**Warp State Display**:
- Clear indication when in "warped" mode
- Balance and payments as of warped date
- Fines applied up to that point
- Visual distinction between past/present/future

### Section 5: Interactive Visualizations
**Purpose**: Multi-chart dashboard showing loan evolution

#### Chart 1: Balance Over Time
**Type**: Line chart with dual y-axis
**Data Series**:
- Principal balance (primary y-axis)
- Outstanding fines (secondary y-axis)
- Total balance (combined)

**Interactive Features**:
- Hover tooltips with exact values
- Zoom and pan capabilities
- Toggle series visibility
- Time machine integration (vertical line indicator)

#### Chart 2: Payment Allocation Breakdown
**Type**: Stacked bar chart
**Data Series**:
- Fine payments (red)
- Interest payments (orange)
- Principal payments (blue)

**Features**:
- Each bar represents one payment
- Hover shows allocation details
- Cumulative totals display

#### Chart 3: Cash Flow Timeline
**Type**: Timeline chart with markers
**Data Series**:
- Expected payments (scheduled)
- Actual payments (recorded)
- Fine applications (penalty events)

**Visual Elements**:
- Different markers for different event types
- Color coding for on-time vs late payments
- Size indicates payment amount

#### Chart 4: Fine Accumulation (if applicable)
**Type**: Step chart
**Data Series**:
- Cumulative fines applied
- Cumulative fines paid
- Outstanding fines balance

**Conditional Display**:
- Only show if fines have been applied
- Clear indication of fine-free loans

### Section 6: Summary & Analysis
**Purpose**: Key metrics and insights display

**Metrics Displayed**:
- Total interest paid vs expected
- Total fines paid (if any)
- Effective interest rate (including fines)
- Days ahead/behind schedule
- Projected payoff date

**Analysis Features**:
- Comparison with original loan terms
- Impact of early/late payments
- Fine avoidance scenarios

## Implementation Phases

### Phase 1: Foundation (Core Structure)
**Tasks**:
1. Create notebook file structure
2. Set up imports and utility functions
3. Implement basic loan creation form
4. Create simple balance display

**Deliverable**: Working loan creation with basic output

### Phase 2: Payment Interface
**Tasks**:
1. Build payment recording widgets
2. Implement payment validation
3. Add payment history display
4. Connect to loan payment recording

**Deliverable**: Functional payment recording system

### Phase 3: Basic Visualization
**Tasks**:
1. Create balance over time chart
2. Implement chart updates on payment
3. Add basic interactivity (hover, zoom)
4. Style charts with consistent theme

**Deliverable**: Interactive balance visualization

### Phase 4: Time Machine Integration
**Tasks**:
1. Implement date slider widget
2. Connect to Warp functionality
3. Update charts for time travel
4. Add warp state indicators

**Deliverable**: Working time machine with visual feedback

### Phase 5: Advanced Charts
**Tasks**:
1. Add payment allocation chart
2. Create cash flow timeline
3. Implement fine tracking chart
4. Add chart controls and toggles

**Deliverable**: Complete visualization dashboard

### Phase 6: Polish & Integration
**Tasks**:
1. Improve styling and layout
2. Add error handling and validation
3. Create summary analysis section
4. Add documentation and help text

**Deliverable**: Production-ready interactive notebook

## Technical Considerations

### State Management
- **Loan Object**: Central state holder
- **Widget Synchronization**: Ensure UI reflects loan state
- **Time Machine State**: Track warped vs present mode
- **Chart Updates**: Efficient re-rendering on state changes

### Performance Optimization
- **Lazy Chart Updates**: Only redraw when necessary
- **Data Caching**: Cache expensive calculations
- **Selective Rendering**: Update only changed chart elements
- **Memory Management**: Clean up old chart data

### Error Handling
- **Input Validation**: Prevent invalid loan parameters
- **Payment Validation**: Ensure valid payment amounts/dates
- **Warp Validation**: Handle invalid time travel dates
- **Graceful Degradation**: Show helpful error messages

### User Experience
- **Progressive Disclosure**: Show advanced features gradually
- **Visual Feedback**: Clear indication of actions and states
- **Responsive Design**: Work on different screen sizes
- **Accessibility**: Proper labels and keyboard navigation

## Data Flow Architecture

```
User Input (Widgets)
    ↓
Validation Layer
    ↓
Loan Object (money-warp)
    ↓
Data Processing (pandas)
    ↓
Chart Updates (plotly)
    ↓
Visual Display (notebook)
```

### Key Data Transformations
1. **Widget Values → Loan Parameters**: Form data to loan constructor
2. **Loan State → Chart Data**: Extract time series for visualization
3. **Time Machine → Filtered Data**: Warp-aware data extraction
4. **Payment Events → Visual Updates**: Real-time chart updates

## Success Criteria

### Functional Requirements
- ✅ Create loans with all supported parameters
- ✅ Record payments with automatic allocation
- ✅ Use time machine to view historical states
- ✅ Display interactive charts with real-time updates
- ✅ Handle late payments and fine calculations

### User Experience Requirements
- ✅ Intuitive interface requiring no technical knowledge
- ✅ Immediate visual feedback for all actions
- ✅ Clear indication of loan state and time position
- ✅ Helpful error messages and validation
- ✅ Professional appearance and smooth interactions

### Technical Requirements
- ✅ Efficient performance with reasonable loan sizes
- ✅ Proper integration with money-warp library
- ✅ Clean, maintainable code structure
- ✅ Comprehensive error handling
- ✅ Cross-browser compatibility (Jupyter environments)

## Future Enhancements (Out of Scope)

### Advanced Features
- Multiple loan comparison
- Loan refinancing scenarios
- Export capabilities (PDF reports)
- Loan optimization recommendations
- Integration with external data sources

### Technical Improvements
- Real-time collaboration features
- Cloud deployment options
- Mobile-responsive design
- Advanced analytics and forecasting
- API integration capabilities

## Risk Mitigation

### Potential Risks
1. **Widget Complexity**: Too many controls overwhelming users
2. **Performance Issues**: Slow chart updates with large datasets
3. **Time Machine Confusion**: Users getting lost in time travel
4. **Data Synchronization**: UI and loan state getting out of sync

### Mitigation Strategies
1. **Progressive Disclosure**: Start simple, add complexity gradually
2. **Performance Testing**: Benchmark with realistic loan scenarios
3. **Clear Visual Indicators**: Always show current time position
4. **Robust State Management**: Single source of truth pattern

## Dependencies and Prerequisites

### Required Packages
```python
# Core money-warp functionality
money-warp  # Our existing library

# Jupyter and widgets
jupyter
ipywidgets>=7.6.0
jupyterlab-widgets  # For JupyterLab compatibility

# Visualization and data
plotly>=5.0.0
pandas>=1.3.0
numpy>=1.20.0

# Date and time handling
python-dateutil>=2.8.0
```

### Development Environment
- Python 3.8+ (compatible with money-warp)
- Jupyter Lab or Notebook
- Modern web browser with JavaScript enabled
- Sufficient memory for interactive charts (>= 4GB recommended)

---

**Document Version**: 1.0  
**Created**: October 3, 2025  
**Status**: Planning Complete - Ready for Implementation  
**Estimated Development Time**: 2-3 days  
**Target Audience**: Financial analysts, loan officers, educational users
