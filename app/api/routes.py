# # app/api/routes.py (continued)
# from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
# from fastapi.responses import JSONResponse
# from typing import Dict, Any, Optional
# from app.core.logging_config import logger
# from app.ml.prediction import PredictionService
# from app.ml.data_processing import AdvancedDataProcessor, DatasetValidator
# from app.ml.model_selection import ModelSelector
# from app.ml.model_training import ModelTrainer
# from app.core.config import settings
# import pandas as pd
# import json

# router = APIRouter()
# prediction_service = PredictionService()

# @router.post("/upload")
# async def upload_dataset(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...),
#     model_name: Optional[str] = None
# ) -> JSONResponse:
#     """
#     Upload and process a dataset, then train a model
#     """
#     try:
#         # Validate file
#         validator = DatasetValidator()
#         if not validator.validate_file_format(file):
#             raise HTTPException(
#                 status_code=400,
#                 detail="Invalid file format. Supported formats: CSV, XLSX, Parquet"
#             )

#         # Process data
#         processor = AdvancedDataProcessor()
#         results = await processor.process_data(file)

#         # Select and train model
#         selector = ModelSelector()
#         model, problem_type = selector.select_model(results.processed_df)

#         trainer = ModelTrainer(model, problem_type)
#         trained_model, metrics = trainer.train(
#             results.processed_df.drop('target', axis=1),
#             results.processed_df['target']
#         )

#         # Schedule background monitoring
#         background_tasks.add_task(
#             start_model_monitoring,
#             trained_model,
#             results.processed_df,
#             problem_type
#         )

#         return JSONResponse({
#             "status": "success",
#             "message": "Model trained successfully",
#             "model_info": {
#                 "type": type(trained_model).__name__,
#                 "problem_type": problem_type,
#                 "metrics": metrics,
#                 "feature_importance": results.feature_importance,
#                 "warnings": results.warnings
#             },
#             "profile_report_url": f"/static/{results.profile_path}"
#         })

#     except Exception as e:
#         logger.error(f"Error processing upload: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/predict")
# async def make_prediction(input_data: Dict[str, Any]) -> JSONResponse:
#     """
#     Make a prediction using the trained model
#     """
#     try:
#         prediction = prediction_service.predict(input_data)
#         return JSONResponse({
#             "status": "success",
#             "prediction": prediction
#         })
#     except Exception as e:
#         logger.error(f"Prediction error: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.get("/model/info")
# async def get_model_info() -> JSONResponse:
#     """
#     Get current model information and metrics
#     """
#     try:
#         model_info = prediction_service.get_model_info()
#         return JSONResponse(model_info)
#     except Exception as e:
#         logger.error(f"Error getting model info: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.get("/model/performance")
# async def get_model_performance() -> JSONResponse:
#     """
#     Get model performance metrics and monitoring data
#     """
#     try:
#         performance_data = prediction_service.monitor.generate_monitoring_report()
#         return JSONResponse(performance_data)
#     except Exception as e:
#         logger.error(f"Error getting performance data: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# # Utility functions
# def start_model_monitoring(model, data, problem_type):
#     """Background task for model monitoring"""
#     try:
#         monitor = ModelMonitor(model.model_id)
#         monitor.initialize_monitoring(data, problem_type)
#     except Exception as e:
#         logger.error(f"Error starting monitoring: {str(e)}")










# app/api/routes.py
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.db.database import get_db
from app.ml.data_processing import AdvancedDataProcessor
from app.ml.model_selection import ModelSelector
from app.ml.model_training import ModelTrainer
from app.ml.prediction import PredictionService
from app.visualization.dashboard import DashboardGenerator
from app.utils.alerts import AlertSystem
from app.schemas.model import ModelResponse, PredictionRequest, PredictionResponse
from app.core.logging_config import logger

router = APIRouter()
prediction_service = PredictionService()
alert_system = AlertSystem()

@router.post("/train", response_model=ModelResponse)
async def train_model(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Train a new model with uploaded data"""
    try:
        # Process data
        processor = AdvancedDataProcessor()
        processed_data = await processor.process_data(file)

        # Select best model
        selector = ModelSelector()
        model, problem_type = selector.select_model(processed_data.processed_df)

        # Train model
        trainer = ModelTrainer(model, problem_type)
        trained_model, metrics = trainer.train(
            processed_data.processed_df.drop('target', axis=1),
            processed_data.processed_df['target']
        )

        # Save model and metadata
        model_id = prediction_service.save_model(trained_model, {
            'metrics': metrics,
            'feature_importance': processed_data.feature_importance,
            'problem_type': problem_type
        })

        # Schedule monitoring
        background_tasks.add_task(
            start_model_monitoring,
            model_id,
            processed_data.processed_df
        )

        return ModelResponse(
            model_id=model_id,
            model_type=type(trained_model).__name__,
            parameters=trained_model.get_params(),
            metrics=metrics,
            feature_importance=processed_data.feature_importance
        )

    except Exception as e:
        logger.error(f"Training error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predict", response_model=PredictionResponse)
async def make_prediction(
    request: PredictionRequest,
    db: Session = Depends(get_db)
):
    """Make prediction using trained model"""
    try:
        prediction = prediction_service.predict(request.features)

        # Log prediction
        log_prediction(db, prediction, request.features)

        return PredictionResponse(
            model_id=prediction_service.model_id,
            prediction=prediction,
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/{model_id}")
async def get_dashboard(model_id: str, db: Session = Depends(get_db)):
    """Get model dashboard"""
    try:
        # Get model data
        model_data = prediction_service.get_model_info(model_id)

        # Get performance data
        performance_data = get_model_performance(db, model_id)

        # Get predictions data
        predictions_data = get_predictions_data(db, model_id)

        # Generate dashboard
        dashboard = DashboardGenerator()
        dashboard_html = dashboard.generate_dashboard(
            model_data,
            performance_data,
            predictions_data
        )

        return HTMLResponse(content=dashboard_html)

    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def list_models(db: Session = Depends(get_db)):
    """List all trained models"""
    try:
        models = prediction_service.list_models()
        return models
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Utility functions
def start_model_monitoring(model_id: str, data: pd.DataFrame):
    """Start monitoring for a model"""
    try:
        monitor = ModelMonitor(model_id)
        monitor.initialize_monitoring(data)
    except Exception as e:
        logger.error(f"Monitoring error: {str(e)}")

def log_prediction(db: Session, prediction: float, input_data: Dict[str, Any]):
    """Log prediction to database"""
    try:
        log = PredictionLog(
            model_id=prediction_service.model_id,
            input_data=input_data,
            prediction=prediction
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Error logging prediction: {str(e)}")